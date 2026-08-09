/*
 * Root-only, single-use materialize-and-promote helper for the frozen d85df632
 * N6 Release. It intentionally has no shell, copy, delete, ACL or xattr path.
 */
#include <CommonCrypto/CommonDigest.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/attr.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef RENAME_EXCL
#error "RENAME_EXCL is required"
#endif
#ifndef RENAME_NOFOLLOW_ANY
#error "RENAME_NOFOLLOW_ANY is required"
#endif
#ifndef RENAME_RESOLVE_BENEATH
#error "RENAME_RESOLVE_BENEATH is required"
#endif

static const char kReleaseRoot[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track";
static const char kArchive[] = "/tmp/n6_release_d85_20260726/source.tar";
static const char kManifest[] =
    "/tmp/n6_release_d85_20260726/release-manifest.json";
static const char kAttestationDir[] =
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/manifests";
static const char kArchiveSha[] =
    "49fb8729e6648f2b15e20d699d5f0f10a97bc1cbd5935cc31f5bb90a9de859ac";
static const char kManifestSha[] =
    "df698d8208977cd5a1d24c144260eb6ef0604f39be1f33f0b08af387027b6106";
static const char kCommit[] = "d85df6328bde223e912dabc3bd65e16df984aa45";
static const char kTree[] = "d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1";
static const char kFilesystemSha[] =
    "5f600a1e1fbb7905968312387c0fc17acee09968a6dfb7d238a22d8d49152ad4";
static const unsigned kExpectedFiles = 6240;
static const unsigned kExpectedDirectories = 45;

static bool safe_relative_path(const char *path);

/* POSIX/PAX only: unknown headers, links and malformed extensions are rejected. */
struct tar_header {
    char name[100]; char mode[8]; char uid[8]; char gid[8]; char size[12];
    char mtime[12]; char checksum[8]; char typeflag; char linkname[100];
    char magic[6]; char version[2]; char uname[32]; char gname[32];
    char devmajor[8]; char devminor[8]; char prefix[155]; char padding[12];
};

static bool read_full(int fd, void *buffer, size_t bytes) {
    unsigned char *p = buffer;
    while (bytes > 0) {
        ssize_t got = read(fd, p, bytes);
        if (got <= 0) return false;
        p += got; bytes -= (size_t)got;
    }
    return true;
}

static bool all_zero(const unsigned char *p, size_t bytes) {
    for (size_t i = 0; i < bytes; ++i) if (p[i] != 0) return false;
    return true;
}

static bool parse_octal(const char *text, size_t bytes, unsigned long long *out) {
    unsigned long long value = 0; bool seen = false;
    for (size_t i = 0; i < bytes; ++i) {
        if (text[i] == '\0' || text[i] == ' ') break;
        if (text[i] < '0' || text[i] > '7' || value > (ULLONG_MAX >> 3)) return false;
        value = (value << 3) | (unsigned long long)(text[i] - '0'); seen = true;
    }
    *out = value;
    return seen;
}

static bool archive_mode_allowed(char typeflag, mode_t mode) {
    if (typeflag == '5') return mode == 0755 || mode == 0775;
    if (typeflag == '\0' || typeflag == '0') {
        return mode == 0644 || mode == 0664 || mode == 0755 || mode == 0775;
    }
    return false;
}

struct pax_override {
    char path[PATH_MAX];
    bool has_path;
};

static bool pax_records(const unsigned char *data, size_t length, bool global,
                        struct pax_override *override) {
    size_t offset = 0;
    while (offset < length) {
        size_t digits = 0; unsigned long long record_length = 0;
        while (offset + digits < length && data[offset + digits] >= '0' &&
               data[offset + digits] <= '9') {
            if (record_length > (SIZE_MAX / 10)) return false;
            record_length = record_length * 10 + (unsigned)(data[offset + digits] - '0');
            ++digits;
        }
        if (digits == 0 || offset + digits >= length || data[offset + digits] != ' ' ||
            record_length < digits + 3 || record_length > length - offset) return false;
        size_t end = offset + (size_t)record_length;
        if (data[end - 1] != '\n') return false;
        size_t key_start = offset + digits + 1;
        size_t equals = key_start;
        while (equals < end - 1 && data[equals] != '=') ++equals;
        if (equals == key_start || equals >= end - 1) return false;
        size_t value_start = equals + 1;
        size_t value_length = end - 1 - value_start;
        if (memchr(data + key_start, '\0', equals - key_start) != NULL ||
            memchr(data + value_start, '\0', value_length) != NULL) return false;
        bool is_comment = equals - key_start == 7 &&
                          memcmp(data + key_start, "comment", 7) == 0;
        bool is_path = equals - key_start == 4 &&
                       memcmp(data + key_start, "path", 4) == 0;
        if ((global && !is_comment) || (!global && !is_path)) return false;
        if (is_comment) {
            if (value_length != strlen(kCommit) ||
                memcmp(data + value_start, kCommit, value_length) != 0) return false;
        } else {
            if (value_length == 0 || value_length >= sizeof(override->path)) return false;
            memcpy(override->path, data + value_start, value_length);
            override->path[value_length] = '\0';
            if (!safe_relative_path(override->path)) return false;
            override->has_path = true;
        }
        offset = end;
    }
    return offset == length;
}

static bool tar_path(const struct tar_header *header, char out[PATH_MAX]) {
    size_t name_n = strnlen(header->name, sizeof(header->name));
    size_t prefix_n = strnlen(header->prefix, sizeof(header->prefix));
    /* USTAR permits a path component to occupy the complete 100-byte name field. */
    if (prefix_n == sizeof(header->prefix)) return false;
    int n = prefix_n ? snprintf(out, PATH_MAX, "%.*s/%.*s", (int)prefix_n,
        header->prefix, (int)name_n, header->name) : snprintf(out, PATH_MAX,
        "%.*s", (int)name_n, header->name);
    if (n > 0 && n < PATH_MAX && out[n - 1] == '/') out[--n] = '\0';
    return n > 0 && n < PATH_MAX && safe_relative_path(out);
}

static bool child_name(const char *name, bool staging) {
    const char *prefix = staging ? ".staging__" : "20";
    return name != NULL && name[0] != '\0' && strchr(name, '/') == NULL &&
           strcmp(name, ".") != 0 && strcmp(name, "..") != 0 &&
           strncmp(name, prefix, strlen(prefix)) == 0;
}

static bool safe_relative_path(const char *path) {
    if (path == NULL || path[0] == '/' || path[0] == '\0' || strstr(path, "//")) {
        return false;
    }
    const char *part = path;
    while (true) {
        const char *slash = strchr(part, '/');
        size_t n = slash == NULL ? strlen(part) : (size_t)(slash - part);
        if (n == 0 || (n == 1 && part[0] == '.') ||
            (n == 2 && part[0] == '.' && part[1] == '.')) {
            return false;
        }
        if (slash == NULL) {
            return true;
        }
        part = slash + 1;
    }
}

static bool sha256_file(const char *path, char out[65]) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_CTX ctx;
    unsigned char buffer[32768];
    ssize_t count;
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return false;
    CC_SHA256_Init(&ctx);
    while ((count = read(fd, buffer, sizeof(buffer))) > 0) {
        CC_SHA256_Update(&ctx, buffer, (CC_LONG)count);
    }
    if (count < 0 || close(fd) != 0) return false;
    CC_SHA256_Final(digest, &ctx);
    for (unsigned i = 0; i < sizeof(digest); ++i) sprintf(out + i * 2, "%02x", digest[i]);
    out[64] = '\0';
    return true;
}

static bool manifest_is_frozen(void) {
    char hash[65];
    if (!sha256_file(kManifest, hash) || strcmp(hash, kManifestSha) != 0) return false;
    int fd = open(kManifest, O_RDONLY | O_NOFOLLOW);
    char text[2048] = {0};
    ssize_t n = fd < 0 ? -1 : read(fd, text, sizeof(text) - 1);
    if (fd < 0 || n < 0 || close(fd) != 0) return false;
    return strstr(text, kCommit) && strstr(text, kTree) &&
           strstr(text, kArchiveSha) && strstr(text, kFilesystemSha);
}

static int open_parent(int rootfd, const char *path, char base[NAME_MAX + 1]) {
    int current = dup(rootfd);
    const char *segment = path;
    const char *slash;
    if (current < 0) return -1;
    while ((slash = strchr(segment, '/')) != NULL) {
        size_t n = (size_t)(slash - segment);
        char part[NAME_MAX + 1];
        if (n == 0 || n > NAME_MAX) goto fail;
        memcpy(part, segment, n); part[n] = '\0';
        if (mkdirat(current, part, 0755) != 0 && errno != EEXIST) goto fail;
        int next = openat(current, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
        if (next < 0) goto fail;
        close(current); current = next; segment = slash + 1;
    }
    if (strlen(segment) == 0 || strlen(segment) > NAME_MAX) goto fail;
    strcpy(base, segment);
    return current;
fail:
    close(current);
    return -1;
}

static bool stream_file(int tarfd, int parentfd, const char *base, mode_t mode,
                        unsigned long long remaining) {
    int fd = openat(parentfd, base, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, mode);
    if (fd < 0) return false;
    char buffer[32768];
    bool ok = true;
    while (remaining > 0) {
        size_t want = remaining > sizeof(buffer) ? sizeof(buffer) : (size_t)remaining;
        if (!read_full(tarfd, buffer, want)) { ok = false; break; }
        const char *p = buffer;
        size_t left = want;
        while (left > 0) {
            ssize_t written = write(fd, p, left);
            if (written <= 0) { ok = false; break; }
            p += written; left -= (size_t)written;
        }
        if (!ok) break;
        remaining -= want;
    }
    mode_t sealed_mode = (mode == 0755 || mode == 0775) ? 0555 : 0444;
    if (fchmod(fd, sealed_mode) != 0 || close(fd) != 0) ok = false;
    return ok;
}

static bool seal_and_count(int dirfd, unsigned *files, unsigned *dirs) {
    DIR *dir = fdopendir(dup(dirfd));
    if (dir == NULL) return false;
    bool ok = true;
    struct dirent *entry;
    while (ok && (entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) continue;
        struct stat st;
        if (fstatat(dirfd, entry->d_name, &st, AT_SYMLINK_NOFOLLOW) != 0) { ok = false; break; }
        if (S_ISLNK(st.st_mode)) { ok = false; break; }
        if (S_ISDIR(st.st_mode)) {
            int child = openat(dirfd, entry->d_name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
            if (child < 0 || !seal_and_count(child, files, dirs) ||
                fchmodat(dirfd, entry->d_name, 0555, 0) != 0) ok = false;
            if (child >= 0) close(child);
            ++*dirs;
        } else if (S_ISREG(st.st_mode) && st.st_nlink <= 1 &&
                   (((st.st_mode & 0777) == 0444) || ((st.st_mode & 0777) == 0555))) {
            ++*files;
        } else {
            ok = false;
        }
    }
    closedir(dir);
    return ok;
}

static bool write_attestation(const char *target) {
    char name[NAME_MAX + 1];
    int n = snprintf(name, sizeof(name), "%s__d85df632-materialize-install.json", target);
    if (n < 0 || (size_t)n >= sizeof(name)) return false;
    int dirfd = open(kAttestationDir, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (dirfd < 0) return false;
    int fd = openat(dirfd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0444);
    if (fd < 0) { close(dirfd); return false; }
    int ok = dprintf(fd,
        "{\"policy_id\":\"n6_immutable_release_privileged_materialize_and_install_v1\","
        "\"commit\":\"%s\",\"tree\":\"%s\",\"archive_sha256\":\"%s\","
        "\"manifest_sha256\":\"%s\",\"filesystem_validation_sha256\":\"%s\","
        "\"target\":\"%s\"}\n", kCommit, kTree, kArchiveSha, kManifestSha,
        kFilesystemSha, target) > 0 && fsync(fd) == 0 && fchmod(fd, 0444) == 0;
    close(fd); close(dirfd);
    return ok;
}

int main(int argc, char *argv[]) {
    if (argc != 5 || geteuid() != 0 || strcmp(argv[1], kArchive) != 0 ||
        strcmp(argv[2], kManifest) != 0 || !child_name(argv[3], true) ||
        !child_name(argv[4], false) || !manifest_is_frozen()) return 64;
    char archive_hash[65];
    if (!sha256_file(kArchive, archive_hash) || strcmp(archive_hash, kArchiveSha) != 0) return 65;
    int rootfd = open(kReleaseRoot, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (rootfd < 0 || mkdirat(rootfd, argv[3], 0755) != 0) return 66;
    struct stat target;
    if (fstatat(rootfd, argv[4], &target, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT) return 67;
    int stagefd = openat(rootfd, argv[3], O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    int tarfd = open(kArchive, O_RDONLY | O_NOFOLLOW);
    if (stagefd < 0 || tarfd < 0) return 68;
    bool ok = true; unsigned headers = 0; struct tar_header header;
    struct pax_override override = {0};
    while (ok && read_full(tarfd, &header, sizeof(header))) {
        if (all_zero((const unsigned char *)&header, sizeof(header))) break;
        char path[PATH_MAX], base[NAME_MAX + 1]; unsigned long long size = 0;
        if (!parse_octal(header.mode, sizeof(header.mode), &size) ||
            header.linkname[0] != '\0') { ok = false; break; }
        mode_t mode = (mode_t)size;
        if (!parse_octal(header.size, sizeof(header.size), &size)) { ok = false; break; }
        unsigned long long payload_size = size;
        if (header.typeflag == 'g' || header.typeflag == 'x') {
            if ((header.typeflag == 'g' && memcmp(header.name, "pax_global_header", 17) != 0) ||
                payload_size > 8192) { ok = false; break; }
            unsigned char payload[8192];
            if (!read_full(tarfd, payload, (size_t)payload_size) ||
                !pax_records(payload, (size_t)payload_size, header.typeflag == 'g', &override)) {
                ok = false; break;
            }
            size_t padding = (size_t)((512 - (payload_size % 512)) % 512);
            unsigned char discard[512];
            if (padding > 0 && !read_full(tarfd, discard, padding)) ok = false;
            ++headers;
            continue;
        }
        if (header.typeflag != '5' && header.typeflag != '\0' && header.typeflag != '0') {
            ok = false; break;
        }
        if (!archive_mode_allowed(header.typeflag, mode)) { ok = false; break; }
        if (override.has_path) {
            strcpy(path, override.path);
            override.has_path = false;
        } else if (!tar_path(&header, path)) {
            ok = false; break;
        }
        int parent = open_parent(stagefd, path, base);
        if (parent < 0) { ok = false; break; }
        if (header.typeflag == '5') {
            if (size != 0 || (mkdirat(parent, base, 0755) != 0 && errno != EEXIST) ||
                fchmodat(parent, base, 0555, 0) != 0) ok = false;
        } else if (header.typeflag == '\0' || header.typeflag == '0') {
            ok = stream_file(tarfd, parent, base, mode, size);
        } else { ok = false; }
        close(parent); ++headers;
        unsigned long long padding = (512 - (size % 512)) % 512;
        unsigned char discard[512];
        if (ok && padding > 0 && !read_full(tarfd, discard, (size_t)padding)) ok = false;
    }
    close(tarfd);
    unsigned files = 0, dirs = 0;
    ok = ok && headers > 0 && seal_and_count(stagefd, &files, &dirs) &&
         files == kExpectedFiles && dirs == kExpectedDirectories &&
         fchmodat(rootfd, argv[3], 0555, 0) == 0;
    const unsigned flags = RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH;
    ok = ok && renameatx_np(rootfd, argv[3], rootfd, argv[4], flags) == 0;
    int targetfd = ok ? openat(rootfd, argv[4], O_RDONLY | O_DIRECTORY | O_NOFOLLOW) : -1;
    ok = ok && targetfd >= 0 && write_attestation(argv[4]);
    if (targetfd >= 0) close(targetfd);
    close(stagefd); close(rootfd);
    return ok ? 0 : 69;
}
