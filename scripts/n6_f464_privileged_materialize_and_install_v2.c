/*
 * User-owned, one-shot recovery4 materializer for the exact immutable f464
 * N6 Release.
 *
 * The historical filename is retained for lineage compatibility; this helper
 * is deliberately non-privileged. It accepts no paths or options and has no
 * elevation, shell, delete, overwrite, service, database, ACL, xattr, or retry
 * path. Failure seals and preserves the one newly-created staging directory.
 * The exact user-owned Release root is writable only during one
 * 0555 -> 0755 -> 0555 owner-write window, with group/other write bits always
 * clear.
 */
#include <CommonCrypto/CommonDigest.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/attr.h>
#include <sys/acl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/xattr.h>
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

static const char kPolicyId[] =
    "n6_f464_recovery4_promote_and_postcondition_governance_v1";
static const char kReleaseParent[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases";
static const char kReleaseRootName[] = "n6-b-track";
static const char kReleaseRootPath[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track";
static const char kCandidateRoot[] =
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kArchive[] =
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62.tar";
static const char kManifest[] =
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62"
    ".git-ls-tree.nul";
static const char kReleaseAttestation[] =
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/"
    "release-attestation.json";
static const char kBundleFile[] =
    "/Users/chuanfuchen/.codex/artifacts/"
    "n6_strategy_center_evaluator_resume_fix_v1/"
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62/"
    "release/config/n6_strategy_center/"
    "N6_SC_TEMPORAL_CONFLUENCE_V2_SHADOW_BUNDLE_20260723.json";
static const char kHistoricalStagingName[] =
    ".staging__20260726_000001__"
    "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kFailedRecovery2StagingName[] =
    ".staging_recovery2__20260726_000001__"
    "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kFailedRecovery3StagingName[] =
    ".staging_recovery3__20260726_000001__"
    "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kStagingName[] =
    ".staging_recovery4__20260726_000001__"
    "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kTargetName[] =
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kCommit[] = "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kTree[] = "c654cbc03c0341c9b3490a02a432b136984c43ce";
static const char kImplementationCommit[] =
    "5c2c38d184385a317afe69b6397f7d98393ff24f";
static const char kImplementationTree[] =
    "0a02ac53513946ca530d3420b2bd06c60630388e";
static const char kArchiveSha[] =
    "a62e98c77e4b3391099ed5eb5939fe2b44a52ac918be3ec6e0a1c6266621d368";
static const char kManifestSha[] =
    "0d29c5b4fa2c550e69806d847a68556a3a6b9b568fe06bfde8027cd4639ff78f";
static const char kFilesystemSha[] =
    "4e46cb1fcd73a452f6a3e534d0bb9dc7ddc011fea4937510991cd9b8e51a79fa";
static const char kAttestationSha[] =
    "0657aad01289cf3ce70635d3732e1408ddad97358ce40c4b570c7de6fed587c3";
static const char kBundleFileSha[] =
    "6efda6309d8e6ebb2d8e91d4a961a0855a76a239c8dd36c45534a50778a190d8";
static const char kBundleInternalSha[] =
    "119296de69f27b840cf743f2d6aad04fe56bd7f1ca80991dbdf5be3f547ca1e0";
static const char kHistoricalPrivilegedHelperTarget[] =
    "/usr/local/libexec/ashare-v3/"
    "n6-f464-immutable-release-materializer-v2";
static const char kStage3NHelperSha[] =
    "63e126e369a8402dfc731a37ba4cf1abf19b73086fada647c2d8a397dca6974c";
static const char kStage3NExitBinding[] =
    "exactly_one_exit_75_primary_73_rename_readonly_secondary_offset_false_negative";
static const dev_t kExpectedDevice = (dev_t)16777232;
static const ino_t kExpectedInode = (ino_t)307341897;
static const ino_t kExpectedHistoricalStagingInode = (ino_t)320375768;
static const ino_t kExpectedFailedRecovery2StagingInode = (ino_t)320422668;
static const ino_t kExpectedFailedRecovery3StagingInode = (ino_t)320439773;
static const uid_t kExpectedUid = (uid_t)501;
static const gid_t kExpectedGid = (gid_t)20;
static const mode_t kRootSealedMode = (mode_t)0555;
static const mode_t kRootOwnerWriteMode = (mode_t)0755;
static const char kExpectedXattrName[] = "com.apple.provenance";
static const char kExpectedXattrFingerprint[] =
    "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea";
static const unsigned kExpectedFiles = 6240;
static const unsigned kExpectedDirectories = 45;
static const unsigned kExpectedPaxGlobalHeaders = 1;
static const unsigned kExpectedPaxExtendedHeaders = 108;
static const unsigned kExpectedFailedRecovery2Files = 572;
static const unsigned kExpectedFailedRecovery2Directories = 8;

struct tar_header {
    char name[100];
    char mode[8];
    char uid[8];
    char gid[8];
    char size[12];
    char mtime[12];
    char checksum[8];
    char typeflag;
    char linkname[100];
    char magic[6];
    char version[2];
    char uname[32];
    char gname[32];
    char devmajor[8];
    char devminor[8];
    char prefix[155];
    char padding[12];
};

struct pax_override {
    char path[PATH_MAX];
    bool has_path;
};

struct manifest_entry {
    char path[PATH_MAX];
    char blob_oid[41];
    mode_t archive_mode;
};

static bool safe_relative_path(const char *path);

enum {
    EXIT_USAGE = 64,
    EXIT_IDENTITY = 65,
    EXIT_FROZEN_INPUT = 66,
    EXIT_ROOT_PREFLIGHT = 67,
    EXIT_TARGET_EXISTS = 68,
    EXIT_STAGING_EXISTS = 69,
    EXIT_ROOT_WINDOW = 70,
    EXIT_STAGING_CREATE = 71,
    EXIT_MATERIALIZE = 72,
    EXIT_PROMOTE = 73,
    EXIT_ROOT_RESTORE = 74,
    EXIT_POSTCONDITION = 75
};

static bool read_full(int fd, void *buffer, size_t bytes) {
    unsigned char *cursor = buffer;
    while (bytes > 0) {
        ssize_t count = read(fd, cursor, bytes);
        if (count <= 0) return false;
        cursor += count;
        bytes -= (size_t)count;
    }
    return true;
}

static bool write_full(int fd, const void *buffer, size_t bytes) {
    const unsigned char *cursor = buffer;
    while (bytes > 0) {
        ssize_t count = write(fd, cursor, bytes);
        if (count <= 0) return false;
        cursor += count;
        bytes -= (size_t)count;
    }
    return true;
}

static bool all_zero(const unsigned char *data, size_t bytes) {
    for (size_t index = 0; index < bytes; ++index) {
        if (data[index] != 0) return false;
    }
    return true;
}

static bool parse_octal(
    const char *text,
    size_t bytes,
    unsigned long long *result
) {
    unsigned long long value = 0;
    size_t index = 0;
    bool seen = false;
    while (index < bytes && text[index] == ' ') ++index;
    for (; index < bytes; ++index) {
        unsigned char character = (unsigned char)text[index];
        if (character == '\0' || character == ' ') break;
        if (character < '0' || character > '7' ||
            value > (ULLONG_MAX >> 3)) {
            return false;
        }
        value = (value << 3) | (unsigned long long)(character - '0');
        seen = true;
    }
    for (; index < bytes; ++index) {
        if (text[index] != '\0' && text[index] != ' ') return false;
    }
    *result = value;
    return seen;
}

static bool valid_tar_checksum(const struct tar_header *header) {
    unsigned long long recorded = 0;
    if (!parse_octal(header->checksum, sizeof(header->checksum), &recorded)) {
        return false;
    }
    const unsigned char *data = (const unsigned char *)header;
    unsigned long long calculated = 0;
    for (size_t index = 0; index < sizeof(*header); ++index) {
        calculated += (index >= 148 && index < 156) ? ' ' : data[index];
    }
    return calculated == recorded;
}

static bool valid_ustar_header(const struct tar_header *header) {
    return memcmp(header->magic, "ustar", 5) == 0 &&
           header->magic[5] == '\0' &&
           memcmp(header->version, "00", 2) == 0 &&
           valid_tar_checksum(header);
}

static bool archive_mode_allowed(char typeflag, mode_t mode) {
    if (typeflag == '5') return mode == 0755 || mode == 0775;
    if (typeflag == '\0' || typeflag == '0') {
        return mode == 0644 || mode == 0664 || mode == 0755 || mode == 0775;
    }
    return false;
}

static bool safe_relative_path(const char *path) {
    if (path == NULL || path[0] == '\0' || path[0] == '/' ||
        strstr(path, "//") != NULL) {
        return false;
    }
    const char *part = path;
    while (true) {
        const char *slash = strchr(part, '/');
        size_t length = slash == NULL ? strlen(part) : (size_t)(slash - part);
        if (length == 0 ||
            (length == 1 && part[0] == '.') ||
            (length == 2 && part[0] == '.' && part[1] == '.')) {
            return false;
        }
        if (slash == NULL) return true;
        part = slash + 1;
    }
}

static bool tar_path(const struct tar_header *header, char result[PATH_MAX]) {
    size_t name_length = strnlen(header->name, sizeof(header->name));
    size_t prefix_length = strnlen(header->prefix, sizeof(header->prefix));
    if (prefix_length == sizeof(header->prefix)) {
        return false;
    }
    int count = prefix_length
        ? snprintf(
              result,
              PATH_MAX,
              "%.*s/%.*s",
              (int)prefix_length,
              header->prefix,
              (int)name_length,
              header->name
          )
        : snprintf(result, PATH_MAX, "%.*s", (int)name_length, header->name);
    if (count > 0 && count < PATH_MAX && result[count - 1] == '/') {
        result[--count] = '\0';
    }
    return count > 0 && count < PATH_MAX && safe_relative_path(result);
}

static bool pax_records(
    const unsigned char *data,
    size_t length,
    bool global,
    struct pax_override *override
) {
    size_t offset = 0;
    unsigned records = 0;
    while (offset < length) {
        size_t digits = 0;
        unsigned long long record_length = 0;
        while (offset + digits < length &&
               data[offset + digits] >= '0' &&
               data[offset + digits] <= '9') {
            if (record_length > SIZE_MAX / 10) return false;
            record_length =
                record_length * 10 + (unsigned)(data[offset + digits] - '0');
            ++digits;
        }
        if (digits == 0 ||
            offset + digits >= length ||
            data[offset + digits] != ' ' ||
            record_length < digits + 3 ||
            record_length > length - offset) {
            return false;
        }
        size_t end = offset + (size_t)record_length;
        if (data[end - 1] != '\n') return false;
        size_t key_start = offset + digits + 1;
        size_t equals = key_start;
        while (equals < end - 1 && data[equals] != '=') ++equals;
        if (equals == key_start || equals >= end - 1) return false;
        size_t value_start = equals + 1;
        size_t value_length = end - 1 - value_start;
        if (memchr(data + key_start, '\0', equals - key_start) != NULL ||
            memchr(data + value_start, '\0', value_length) != NULL) {
            return false;
        }
        bool comment =
            equals - key_start == 7 &&
            memcmp(data + key_start, "comment", 7) == 0;
        bool path =
            equals - key_start == 4 &&
            memcmp(data + key_start, "path", 4) == 0;
        if ((global && !comment) || (!global && !path) || records != 0) {
            return false;
        }
        if (comment) {
            if (value_length != strlen(kCommit) ||
                memcmp(data + value_start, kCommit, value_length) != 0) {
                return false;
            }
        } else {
            if (override->has_path ||
                value_length == 0 ||
                value_length >= sizeof(override->path)) {
                return false;
            }
            memcpy(override->path, data + value_start, value_length);
            override->path[value_length] = '\0';
            if (!safe_relative_path(override->path)) return false;
            override->has_path = true;
        }
        ++records;
        offset = end;
    }
    return offset == length && records == 1;
}

static bool sha256_file(const char *path, char result[65]) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    unsigned char buffer[32768];
    CC_SHA256_CTX context;
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0 || CC_SHA256_Init(&context) != 1) {
        if (fd >= 0) close(fd);
        return false;
    }
    ssize_t count;
    while ((count = read(fd, buffer, sizeof(buffer))) > 0) {
        if (CC_SHA256_Update(&context, buffer, (CC_LONG)count) != 1) {
            close(fd);
            return false;
        }
    }
    bool ok =
        count == 0 &&
        close(fd) == 0 &&
        CC_SHA256_Final(digest, &context) == 1;
    if (!ok) return false;
    for (size_t index = 0; index < sizeof(digest); ++index) {
        snprintf(result + index * 2, 3, "%02x", digest[index]);
    }
    result[64] = '\0';
    return true;
}

static void sha256_u64(CC_SHA256_CTX *context, uint64_t value) {
    unsigned char encoded[8];
    for (size_t index = 0; index < sizeof(encoded); ++index) {
        encoded[sizeof(encoded) - index - 1] =
            (unsigned char)(value & UINT64_C(0xff));
        value >>= 8;
    }
    CC_SHA256_Update(context, encoded, (CC_LONG)sizeof(encoded));
}

static void hex_digest(const unsigned char *digest, char output[65]) {
    static const char digits[] = "0123456789abcdef";
    for (size_t index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        output[index * 2] = digits[digest[index] >> 4];
        output[index * 2 + 1] = digits[digest[index] & 0x0f];
    }
    output[64] = '\0';
}

static bool exact_provenance_xattr_fingerprint(int fd, char output[65]) {
    ssize_t names_size = flistxattr(fd, NULL, 0, 0);
    if (names_size <= 0) return false;
    char *names = malloc((size_t)names_size);
    if (names == NULL) return false;
    if (flistxattr(fd, names, (size_t)names_size, 0) != names_size) {
        free(names);
        return false;
    }
    size_t name_length = strnlen(names, (size_t)names_size);
    if (name_length + 1 != (size_t)names_size ||
        strcmp(names, kExpectedXattrName) != 0) {
        free(names);
        return false;
    }
    ssize_t value_size = fgetxattr(fd, names, NULL, 0, 0, 0);
    if (value_size < 0) {
        free(names);
        return false;
    }
    void *value = malloc(value_size == 0 ? 1 : (size_t)value_size);
    if (value == NULL ||
        fgetxattr(fd, names, value, (size_t)value_size, 0, 0) != value_size) {
        free(value);
        free(names);
        return false;
    }
    CC_SHA256_CTX context;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Init(&context);
    sha256_u64(&context, (uint64_t)name_length);
    CC_SHA256_Update(&context, names, (CC_LONG)name_length);
    sha256_u64(&context, (uint64_t)value_size);
    CC_SHA256_Update(&context, value, (CC_LONG)value_size);
    CC_SHA256_Final(digest, &context);
    hex_digest(digest, output);
    free(value);
    free(names);
    return true;
}

static bool no_extended_acl(int fd) {
    errno = 0;
    acl_t acl = acl_get_fd_np(fd, ACL_TYPE_EXTENDED);
    if (acl == NULL) return errno == ENOENT;
    ssize_t length = 0;
    char *text = acl_to_text(acl, &length);
    bool ok = text != NULL && length == 0 && text[0] == '\0';
    if (text != NULL) acl_free(text);
    acl_free(acl);
    return ok;
}

static bool exact_root_metadata(
    const struct stat *metadata,
    mode_t expected_mode
) {
    return S_ISDIR(metadata->st_mode) &&
           metadata->st_dev == kExpectedDevice &&
           metadata->st_ino == kExpectedInode &&
           metadata->st_uid == kExpectedUid &&
           metadata->st_gid == kExpectedGid &&
           (metadata->st_mode & 07777) == expected_mode;
}

static bool exact_release_entry(
    int fd,
    mode_t expected_mode,
    bool directory
) {
    struct stat metadata;
    char xattr_fingerprint[65];
    return fstat(fd, &metadata) == 0 &&
           (directory ? S_ISDIR(metadata.st_mode) : S_ISREG(metadata.st_mode)) &&
           metadata.st_uid == kExpectedUid &&
           metadata.st_gid == kExpectedGid &&
           (metadata.st_mode & 07777) == expected_mode &&
           (metadata.st_mode & 0222) == 0 &&
           no_extended_acl(fd) &&
           exact_provenance_xattr_fingerprint(fd, xattr_fingerprint) &&
           strcmp(xattr_fingerprint, kExpectedXattrFingerprint) == 0;
}

static bool exact_staging_work_directory(int fd) {
    struct stat metadata;
    char xattr_fingerprint[65];
    return fstat(fd, &metadata) == 0 &&
           S_ISDIR(metadata.st_mode) &&
           metadata.st_uid == kExpectedUid &&
           metadata.st_gid == kExpectedGid &&
           (metadata.st_mode & 07777) == 0700 &&
           (metadata.st_mode & 0077) == 0 &&
           no_extended_acl(fd) &&
           exact_provenance_xattr_fingerprint(fd, xattr_fingerprint) &&
           strcmp(xattr_fingerprint, kExpectedXattrFingerprint) == 0;
}

static bool directory_empty(int fd) {
    int scanfd = openat(
        fd,
        ".",
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (scanfd < 0) return false;
    DIR *directory = fdopendir(scanfd);
    if (directory == NULL) {
        close(scanfd);
        return false;
    }
    bool empty = true;
    struct dirent *item;
    while ((item = readdir(directory)) != NULL) {
        if (strcmp(item->d_name, ".") != 0 &&
            strcmp(item->d_name, "..") != 0) {
            empty = false;
            break;
        }
    }
    closedir(directory);
    return empty;
}

static bool exact_historical_staging(int fd) {
    struct stat metadata;
    char xattr_fingerprint[65];
    return fstat(fd, &metadata) == 0 &&
           S_ISDIR(metadata.st_mode) &&
           metadata.st_dev == kExpectedDevice &&
           metadata.st_ino == kExpectedHistoricalStagingInode &&
           metadata.st_uid == kExpectedUid &&
           metadata.st_gid == kExpectedGid &&
           (metadata.st_mode & 07777) == 0700 &&
           (metadata.st_mode & 0077) == 0 &&
           no_extended_acl(fd) &&
           exact_provenance_xattr_fingerprint(fd, xattr_fingerprint) &&
           strcmp(xattr_fingerprint, kExpectedXattrFingerprint) == 0 &&
           directory_empty(fd);
}

static bool absent_at(int dirfd, const char *name) {
    struct stat metadata;
    if (fstatat(dirfd, name, &metadata, AT_SYMLINK_NOFOLLOW) == 0) return false;
    return errno == ENOENT;
}

static bool absolute_path_absent(const char *path) {
    struct stat metadata;
    if (lstat(path, &metadata) == 0) return false;
    return errno == ENOENT;
}

static bool frozen_inputs_match(void) {
    char archive_hash[65];
    char manifest_hash[65];
    char attestation_hash[65];
    char bundle_hash[65];
    return sha256_file(kArchive, archive_hash) &&
           sha256_file(kManifest, manifest_hash) &&
           sha256_file(kReleaseAttestation, attestation_hash) &&
           sha256_file(kBundleFile, bundle_hash) &&
           strcmp(archive_hash, kArchiveSha) == 0 &&
           strcmp(manifest_hash, kManifestSha) == 0 &&
           strcmp(attestation_hash, kAttestationSha) == 0 &&
           strcmp(bundle_hash, kBundleFileSha) == 0;
}

static bool read_manifest_entry(int fd, struct manifest_entry *entry) {
    unsigned char record[PATH_MAX + 96];
    size_t length = 0;
    while (length < sizeof(record)) {
        ssize_t count = read(fd, record + length, 1);
        if (count != 1) return false;
        if (record[length++] == '\0') break;
    }
    if (length < 50 || length == sizeof(record) || record[length - 1] != '\0') {
        return false;
    }
    record[length - 1] = '\0';
    if (memcmp(record + 6, " blob ", 6) != 0 || record[52] != '\t') return false;
    mode_t mode;
    if (memcmp(record, "100644", 6) == 0) {
        mode = 0644;
    } else if (memcmp(record, "100755", 6) == 0) {
        mode = 0755;
    } else {
        return false;
    }
    for (size_t index = 12; index < 52; ++index) {
        unsigned char character = record[index];
        if (!((character >= '0' && character <= '9') ||
              (character >= 'a' && character <= 'f'))) {
            return false;
        }
    }
    const char *path = (const char *)record + 53;
    if (!safe_relative_path(path) || strlen(path) >= sizeof(entry->path)) {
        return false;
    }
    strcpy(entry->path, path);
    memcpy(entry->blob_oid, record + 12, 40);
    entry->blob_oid[40] = '\0';
    entry->archive_mode = mode;
    return true;
}

static int open_existing_parent(
    int rootfd,
    const char *path,
    char base[NAME_MAX + 1]
) {
    int current = dup(rootfd);
    if (current < 0) return -1;
    const char *segment = path;
    const char *slash;
    while ((slash = strchr(segment, '/')) != NULL) {
        size_t length = (size_t)(slash - segment);
        char part[NAME_MAX + 1];
        if (length == 0 || length > NAME_MAX) goto fail;
        memcpy(part, segment, length);
        part[length] = '\0';
        int next = openat(
            current,
            part,
            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        );
        if (next < 0) goto fail;
        close(current);
        current = next;
        segment = slash + 1;
    }
    if (strlen(segment) == 0 || strlen(segment) > NAME_MAX) goto fail;
    strcpy(base, segment);
    return current;

fail:
    close(current);
    return -1;
}

static bool verify_existing_blob(int fd, const char *expected_blob_oid) {
    struct stat metadata;
    if (fstat(fd, &metadata) != 0 || metadata.st_size < 0) return false;

    char blob_header[64];
    int header_length = snprintf(
        blob_header,
        sizeof(blob_header),
        "blob %lld",
        (long long)metadata.st_size
    );
    if (header_length <= 0 || (size_t)header_length + 1 >= sizeof(blob_header)) {
        return false;
    }

    CC_SHA1_CTX context;
    unsigned char digest[CC_SHA1_DIGEST_LENGTH];
    bool ok =
        CC_SHA1_Init(&context) == 1 &&
        CC_SHA1_Update(
            &context,
            blob_header,
            (CC_LONG)((size_t)header_length + 1)
        ) == 1;
    unsigned char buffer[32768];
    ssize_t count;
    while (ok && (count = read(fd, buffer, sizeof(buffer))) > 0) {
        ok = CC_SHA1_Update(&context, buffer, (CC_LONG)count) == 1;
    }
    ok = ok && count == 0 && CC_SHA1_Final(digest, &context) == 1;
    if (!ok) return false;

    char actual_oid[41];
    for (size_t index = 0; index < sizeof(digest); ++index) {
        snprintf(actual_oid + index * 2, 3, "%02x", digest[index]);
    }
    actual_oid[40] = '\0';
    return strcmp(actual_oid, expected_blob_oid) == 0;
}

static bool exact_failed_recovery2_entry(
    int fd,
    mode_t expected_mode,
    bool directory
) {
    struct stat metadata;
    char xattr_fingerprint[65];
    return fstat(fd, &metadata) == 0 &&
           (directory ? S_ISDIR(metadata.st_mode) : S_ISREG(metadata.st_mode)) &&
           metadata.st_uid == kExpectedUid &&
           metadata.st_gid == kExpectedGid &&
           (metadata.st_mode & 07777) == expected_mode &&
           (metadata.st_mode & 0022) == 0 &&
           no_extended_acl(fd) &&
           exact_provenance_xattr_fingerprint(fd, xattr_fingerprint) &&
           strcmp(xattr_fingerprint, kExpectedXattrFingerprint) == 0;
}

static bool count_failed_recovery2_tree(
    int dirfd,
    unsigned *files,
    unsigned *directories
) {
    int scanfd = openat(
        dirfd,
        ".",
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (scanfd < 0) return false;
    DIR *directory = fdopendir(scanfd);
    if (directory == NULL) {
        close(scanfd);
        return false;
    }
    bool ok = true;
    struct dirent *item;
    while (ok && (item = readdir(directory)) != NULL) {
        if (strcmp(item->d_name, ".") == 0 ||
            strcmp(item->d_name, "..") == 0) {
            continue;
        }
        struct stat metadata;
        if (fstatat(
                dirfd,
                item->d_name,
                &metadata,
                AT_SYMLINK_NOFOLLOW
            ) != 0 ||
            S_ISLNK(metadata.st_mode)) {
            ok = false;
            break;
        }
        if (S_ISDIR(metadata.st_mode)) {
            int child = openat(
                dirfd,
                item->d_name,
                O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
            );
            if (child < 0 ||
                !exact_failed_recovery2_entry(child, 0755, true) ||
                !count_failed_recovery2_tree(child, files, directories)) {
                ok = false;
            }
            if (child >= 0) close(child);
            ++*directories;
        } else if (S_ISREG(metadata.st_mode)) {
            mode_t mode = (mode_t)(metadata.st_mode & 07777);
            int filefd = openat(
                dirfd,
                item->d_name,
                O_RDONLY | O_NOFOLLOW | O_CLOEXEC
            );
            if ((mode != 0444 && mode != 0555) ||
                filefd < 0 ||
                !exact_failed_recovery2_entry(filefd, mode, false)) {
                ok = false;
            }
            if (filefd >= 0) close(filefd);
            ++*files;
        } else {
            ok = false;
        }
    }
    closedir(directory);
    return ok;
}

static bool exact_failed_recovery2_staging(int fd) {
    struct stat metadata;
    char xattr_fingerprint[65];
    if (fstat(fd, &metadata) != 0 ||
        !S_ISDIR(metadata.st_mode) ||
        metadata.st_dev != kExpectedDevice ||
        metadata.st_ino != kExpectedFailedRecovery2StagingInode ||
        metadata.st_uid != kExpectedUid ||
        metadata.st_gid != kExpectedGid ||
        (metadata.st_mode & 07777) != 0700 ||
        (metadata.st_mode & 0077) != 0 ||
        !no_extended_acl(fd) ||
        !exact_provenance_xattr_fingerprint(fd, xattr_fingerprint) ||
        strcmp(xattr_fingerprint, kExpectedXattrFingerprint) != 0) {
        return false;
    }

    int manifestfd = open(kManifest, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (manifestfd < 0) return false;
    bool ok = true;
    for (unsigned index = 0;
         ok && index < kExpectedFailedRecovery2Files;
         ++index) {
        struct manifest_entry entry = {0};
        char base[NAME_MAX + 1];
        int parentfd = -1;
        int filefd = -1;
        ok = read_manifest_entry(manifestfd, &entry);
        if (ok) parentfd = open_existing_parent(fd, entry.path, base);
        if (parentfd >= 0) {
            filefd = openat(
                parentfd,
                base,
                O_RDONLY | O_NOFOLLOW | O_CLOEXEC
            );
        }
        mode_t expected_mode =
            entry.archive_mode == 0755 ? (mode_t)0555 : (mode_t)0444;
        ok =
            ok &&
            parentfd >= 0 &&
            filefd >= 0 &&
            exact_failed_recovery2_entry(filefd, expected_mode, false) &&
            verify_existing_blob(filefd, entry.blob_oid);
        if (filefd >= 0) close(filefd);
        if (parentfd >= 0) close(parentfd);
    }
    close(manifestfd);

    unsigned files = 0;
    unsigned directories = 0;
    return ok &&
           count_failed_recovery2_tree(fd, &files, &directories) &&
           files == kExpectedFailedRecovery2Files &&
           directories == kExpectedFailedRecovery2Directories;
}

static bool count_exact_release_tree(
    int dirfd,
    unsigned *files,
    unsigned *directories
) {
    int scanfd = openat(
        dirfd,
        ".",
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (scanfd < 0) return false;
    DIR *directory = fdopendir(scanfd);
    if (directory == NULL) {
        close(scanfd);
        return false;
    }
    bool ok = true;
    struct dirent *item;
    while (ok && (item = readdir(directory)) != NULL) {
        if (strcmp(item->d_name, ".") == 0 ||
            strcmp(item->d_name, "..") == 0) {
            continue;
        }
        struct stat metadata;
        if (fstatat(
                dirfd,
                item->d_name,
                &metadata,
                AT_SYMLINK_NOFOLLOW
            ) != 0 ||
            S_ISLNK(metadata.st_mode)) {
            ok = false;
            break;
        }
        if (S_ISDIR(metadata.st_mode)) {
            int child = openat(
                dirfd,
                item->d_name,
                O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
            );
            if (child < 0 ||
                !exact_release_entry(child, 0555, true) ||
                !count_exact_release_tree(child, files, directories)) {
                ok = false;
            }
            if (child >= 0) close(child);
            ++*directories;
        } else if (
            S_ISREG(metadata.st_mode) &&
            metadata.st_nlink == 1 &&
            ((metadata.st_mode & 07777) == 0444 ||
             (metadata.st_mode & 07777) == 0555)
        ) {
            mode_t mode = (mode_t)(metadata.st_mode & 07777);
            int filefd = openat(
                dirfd,
                item->d_name,
                O_RDONLY | O_NOFOLLOW | O_CLOEXEC
            );
            if (filefd < 0 ||
                !exact_release_entry(filefd, mode, false)) {
                ok = false;
            } else {
                ++*files;
            }
            if (filefd >= 0) close(filefd);
        } else {
            ok = false;
        }
    }
    closedir(directory);
    return ok;
}

static bool verify_full_manifest_tree(int fd) {
    int manifestfd = open(kManifest, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (manifestfd < 0) return false;
    bool ok = true;
    for (unsigned index = 0; ok && index < kExpectedFiles; ++index) {
        struct manifest_entry entry = {0};
        char base[NAME_MAX + 1];
        int parentfd = -1;
        int filefd = -1;
        ok = read_manifest_entry(manifestfd, &entry);
        if (ok) parentfd = open_existing_parent(fd, entry.path, base);
        if (parentfd >= 0) {
            filefd = openat(
                parentfd,
                base,
                O_RDONLY | O_NOFOLLOW | O_CLOEXEC
            );
        }
        mode_t expected_mode =
            entry.archive_mode == 0755 ? (mode_t)0555 : (mode_t)0444;
        ok =
            ok &&
            parentfd >= 0 &&
            filefd >= 0 &&
            exact_release_entry(filefd, expected_mode, false) &&
            verify_existing_blob(filefd, entry.blob_oid);
        if (filefd >= 0) close(filefd);
        if (parentfd >= 0) close(parentfd);
    }
    unsigned char extra_manifest_byte;
    ok = ok && read(manifestfd, &extra_manifest_byte, 1) == 0;
    close(manifestfd);
    return ok;
}

static bool exact_sealed_full_release_tree(int fd) {
    unsigned files = 0;
    unsigned directories = 0;
    return exact_release_entry(fd, 0555, true) &&
           verify_full_manifest_tree(fd) &&
           count_exact_release_tree(fd, &files, &directories) &&
           files == kExpectedFiles &&
           directories == kExpectedDirectories;
}

static bool exact_failed_recovery3_staging(int fd) {
    struct stat metadata;
    return fstat(fd, &metadata) == 0 &&
           metadata.st_dev == kExpectedDevice &&
           metadata.st_ino == kExpectedFailedRecovery3StagingInode &&
           exact_sealed_full_release_tree(fd);
}

static int open_parent(int rootfd, const char *path, char base[NAME_MAX + 1]) {
    int current = dup(rootfd);
    if (current < 0) return -1;
    const char *segment = path;
    const char *slash;
    while ((slash = strchr(segment, '/')) != NULL) {
        size_t length = (size_t)(slash - segment);
        char part[NAME_MAX + 1];
        if (length == 0 || length > NAME_MAX) goto fail;
        memcpy(part, segment, length);
        part[length] = '\0';
        if (mkdirat(current, part, 0755) != 0 && errno != EEXIST) goto fail;
        int next = openat(current, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
        if (next < 0) goto fail;
        close(current);
        current = next;
        segment = slash + 1;
    }
    if (strlen(segment) == 0 || strlen(segment) > NAME_MAX) goto fail;
    strcpy(base, segment);
    return current;

fail:
    close(current);
    return -1;
}

static bool stream_and_verify_file(
    int tarfd,
    int parentfd,
    const char *base,
    mode_t archive_mode,
    unsigned long long size,
    const char *expected_blob_oid
) {
    mode_t create_mode = archive_mode == 0755 || archive_mode == 0775
        ? 0700
        : 0600;
    mode_t sealed_mode = create_mode == 0700 ? 0555 : 0444;
    int fd = openat(
        parentfd,
        base,
        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW,
        create_mode
    );
    if (fd < 0) return false;

    char blob_header[64];
    int header_length =
        snprintf(blob_header, sizeof(blob_header), "blob %llu", size);
    if (header_length <= 0 || (size_t)header_length + 1 >= sizeof(blob_header)) {
        close(fd);
        return false;
    }

    CC_SHA1_CTX context;
    unsigned char digest[CC_SHA1_DIGEST_LENGTH];
    bool ok =
        CC_SHA1_Init(&context) == 1 &&
        CC_SHA1_Update(
            &context,
            blob_header,
            (CC_LONG)((size_t)header_length + 1)
        ) == 1;
    unsigned char buffer[32768];
    unsigned long long remaining = size;
    while (ok && remaining > 0) {
        size_t wanted =
            remaining > sizeof(buffer) ? sizeof(buffer) : (size_t)remaining;
        ok =
            read_full(tarfd, buffer, wanted) &&
            write_full(fd, buffer, wanted) &&
            CC_SHA1_Update(&context, buffer, (CC_LONG)wanted) == 1;
        remaining -= wanted;
    }
    ok =
        ok &&
        CC_SHA1_Final(digest, &context) == 1 &&
        fsync(fd) == 0 &&
        fchmod(fd, sealed_mode) == 0 &&
        exact_release_entry(fd, sealed_mode, false);
    int close_result = close(fd);
    ok = ok && close_result == 0;
    if (!ok) return false;

    char actual_oid[41];
    for (size_t index = 0; index < sizeof(digest); ++index) {
        snprintf(actual_oid + index * 2, 3, "%02x", digest[index]);
    }
    actual_oid[40] = '\0';
    return strcmp(actual_oid, expected_blob_oid) == 0;
}

static bool seal_and_count(int dirfd, unsigned *files, unsigned *directories) {
    int scanfd = openat(
        dirfd,
        ".",
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (scanfd < 0) return false;
    DIR *directory = fdopendir(scanfd);
    if (directory == NULL) {
        close(scanfd);
        return false;
    }
    bool ok = true;
    struct dirent *item;
    while (ok && (item = readdir(directory)) != NULL) {
        if (strcmp(item->d_name, ".") == 0 ||
            strcmp(item->d_name, "..") == 0) {
            continue;
        }
        struct stat metadata;
        if (fstatat(
                dirfd,
                item->d_name,
                &metadata,
                AT_SYMLINK_NOFOLLOW
            ) != 0 ||
            S_ISLNK(metadata.st_mode)) {
            ok = false;
            break;
        }
        if (S_ISDIR(metadata.st_mode)) {
            int child = openat(
                dirfd,
                item->d_name,
                O_RDONLY | O_DIRECTORY | O_NOFOLLOW
            );
            if (child < 0 ||
                !seal_and_count(child, files, directories) ||
                fchmod(child, 0555) != 0 ||
                fsync(child) != 0 ||
                !exact_release_entry(child, 0555, true)) {
                ok = false;
            }
            if (child >= 0) close(child);
            ++*directories;
        } else if (
            S_ISREG(metadata.st_mode) &&
            metadata.st_nlink == 1 &&
            ((metadata.st_mode & 0777) == 0444 ||
             (metadata.st_mode & 0777) == 0555)
        ) {
            int filefd = openat(dirfd, item->d_name, O_RDONLY | O_NOFOLLOW);
            if (filefd < 0 ||
                !exact_release_entry(
                    filefd,
                    (mode_t)(metadata.st_mode & 0777),
                    false
                )) {
                ok = false;
            } else {
                ++*files;
            }
            if (filefd >= 0) close(filefd);
        } else {
            ok = false;
        }
    }
    closedir(directory);
    return ok;
}

static bool extract_and_verify(int rootfd, int stagefd) {
    int tarfd = open(kArchive, O_RDONLY | O_NOFOLLOW);
    int manifestfd = open(kManifest, O_RDONLY | O_NOFOLLOW);
    if (tarfd < 0 || manifestfd < 0) {
        if (tarfd >= 0) close(tarfd);
        if (manifestfd >= 0) close(manifestfd);
        return false;
    }

    bool ok = true;
    bool end_seen = false;
    unsigned files = 0;
    unsigned pax_global = 0;
    unsigned pax_extended = 0;
    struct pax_override override = {0};
    struct tar_header header;

    while (ok && read_full(tarfd, &header, sizeof(header))) {
        if (all_zero((const unsigned char *)&header, sizeof(header))) {
            struct tar_header second_zero;
            ok =
                read_full(tarfd, &second_zero, sizeof(second_zero)) &&
                all_zero((const unsigned char *)&second_zero, sizeof(second_zero));
            unsigned char trailing[32768];
            ssize_t trailing_count;
            while (ok && (trailing_count = read(
                              tarfd,
                              trailing,
                              sizeof(trailing)
                          )) > 0) {
                ok = all_zero(trailing, (size_t)trailing_count);
            }
            ok = ok && trailing_count == 0;
            end_seen = ok;
            break;
        }
        if (!valid_ustar_header(&header) || header.linkname[0] != '\0') {
            ok = false;
            break;
        }
        unsigned long long parsed_mode = 0;
        unsigned long long size = 0;
        if (!parse_octal(header.mode, sizeof(header.mode), &parsed_mode) ||
            !parse_octal(header.size, sizeof(header.size), &size)) {
            ok = false;
            break;
        }
        mode_t mode = (mode_t)parsed_mode;
        if (header.typeflag == 'g' || header.typeflag == 'x') {
            if (mode != 0666 ||
                size == 0 ||
                size > 8192 ||
                (header.typeflag == 'g' &&
                 (pax_global != 0 ||
                  memcmp(header.name, "pax_global_header", 17) != 0)) ||
                (header.typeflag == 'x' && override.has_path)) {
                ok = false;
                break;
            }
            unsigned char payload[8192];
            ok =
                read_full(tarfd, payload, (size_t)size) &&
                pax_records(
                    payload,
                    (size_t)size,
                    header.typeflag == 'g',
                    &override
                );
            unsigned long long padding = (512 - (size % 512)) % 512;
            unsigned char discard[512];
            if (ok && padding > 0) {
                ok = read_full(tarfd, discard, (size_t)padding);
            }
            if (header.typeflag == 'g') {
                ++pax_global;
            } else {
                ++pax_extended;
            }
            continue;
        }
        if (!archive_mode_allowed(header.typeflag, mode)) {
            ok = false;
            break;
        }

        char path[PATH_MAX];
        if (override.has_path) {
            strcpy(path, override.path);
            override.has_path = false;
        } else if (!tar_path(&header, path)) {
            ok = false;
            break;
        }

        char base[NAME_MAX + 1];
        int parentfd = open_parent(stagefd, path, base);
        if (parentfd < 0) {
            ok = false;
            break;
        }
        if (header.typeflag == '5') {
            ok =
                size == 0 &&
                (mkdirat(parentfd, base, 0755) == 0 || errno == EEXIST);
        } else {
            struct manifest_entry entry;
            ok =
                read_manifest_entry(manifestfd, &entry) &&
                strcmp(path, entry.path) == 0 &&
                ((entry.archive_mode == 0644 &&
                  (mode == 0644 || mode == 0664)) ||
                 (entry.archive_mode == 0755 &&
                  (mode == 0755 || mode == 0775))) &&
                stream_and_verify_file(
                    tarfd,
                    parentfd,
                    base,
                    mode,
                    size,
                    entry.blob_oid
                );
            if (ok) ++files;
        }
        close(parentfd);

        unsigned long long padding = (512 - (size % 512)) % 512;
        unsigned char discard[512];
        if (ok && padding > 0) {
            ok = read_full(tarfd, discard, (size_t)padding);
        }
    }

    unsigned char extra_manifest_byte;
    ok =
        ok &&
        end_seen &&
        !override.has_path &&
        files == kExpectedFiles &&
        pax_global == kExpectedPaxGlobalHeaders &&
        pax_extended == kExpectedPaxExtendedHeaders &&
        read(manifestfd, &extra_manifest_byte, 1) == 0;
    close(tarfd);
    close(manifestfd);

    unsigned actual_files = 0;
    unsigned actual_directories = 0;
    ok =
        ok &&
        seal_and_count(stagefd, &actual_files, &actual_directories) &&
        actual_files == kExpectedFiles &&
        actual_directories == kExpectedDirectories &&
        fsync(stagefd) == 0 &&
        exact_staging_work_directory(stagefd);
    (void)rootfd;
    return ok;
}

static void record_postcondition_failure(
    int *postcondition_result,
    int *postcondition_errno,
    int result,
    int saved_errno
) {
    if (*postcondition_result == 0) {
        *postcondition_result = result;
        *postcondition_errno = saved_errno;
    }
}

static int final_exit_code(int primary_result, int postcondition_result) {
    return primary_result != 0 ? primary_result : postcondition_result;
}

int main(int argc, char **argv) {
    (void)argv;
    /* Keep every frozen provenance anchor in the compiled attested binary. */
    const char *provenance[] = {
        kPolicyId,
        kCandidateRoot,
        kCommit,
        kTree,
        kImplementationCommit,
        kImplementationTree,
        kFilesystemSha,
        kAttestationSha,
        kBundleFileSha,
        kBundleInternalSha,
        kStage3NHelperSha,
        kStage3NExitBinding,
    };
    if (argc != 1) return EXIT_USAGE;
    if (getuid() != kExpectedUid ||
        geteuid() != kExpectedUid ||
        getgid() != kExpectedGid ||
        getegid() != kExpectedGid ||
        provenance[0][0] == '\0') {
        return EXIT_IDENTITY;
    }
    if (!frozen_inputs_match()) return EXIT_FROZEN_INPUT;

    int parentfd = open(
        kReleaseParent,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (parentfd < 0) return EXIT_ROOT_PREFLIGHT;
    int rootfd = openat(
        parentfd,
        kReleaseRootName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    char resolved_path[PATH_MAX];
    struct stat path_metadata;
    struct stat root_metadata;
    char root_xattr_before[65];
    if (rootfd < 0 ||
        fcntl(rootfd, F_GETPATH, resolved_path) != 0 ||
        strcmp(resolved_path, kReleaseRootPath) != 0 ||
        fstatat(
            parentfd,
            kReleaseRootName,
            &path_metadata,
            AT_SYMLINK_NOFOLLOW
        ) != 0 ||
        fstat(rootfd, &root_metadata) != 0 ||
        path_metadata.st_dev != root_metadata.st_dev ||
        path_metadata.st_ino != root_metadata.st_ino ||
        !exact_root_metadata(&root_metadata, kRootSealedMode) ||
        !no_extended_acl(rootfd) ||
        !exact_provenance_xattr_fingerprint(rootfd, root_xattr_before) ||
        strcmp(root_xattr_before, kExpectedXattrFingerprint) != 0 ||
        !absolute_path_absent(kHistoricalPrivilegedHelperTarget)) {
        if (rootfd >= 0) close(rootfd);
        close(parentfd);
        return EXIT_ROOT_PREFLIGHT;
    }

    int historical_stagefd = openat(
        rootfd,
        kHistoricalStagingName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    struct stat historical_path_before;
    struct stat historical_fd_before;
    if (historical_stagefd < 0 ||
        fstatat(
            rootfd,
            kHistoricalStagingName,
            &historical_path_before,
            AT_SYMLINK_NOFOLLOW
        ) != 0 ||
        fstat(historical_stagefd, &historical_fd_before) != 0 ||
        historical_path_before.st_dev != historical_fd_before.st_dev ||
        historical_path_before.st_ino != historical_fd_before.st_ino ||
        !exact_historical_staging(historical_stagefd)) {
        if (historical_stagefd >= 0) close(historical_stagefd);
        close(rootfd);
        close(parentfd);
        return EXIT_STAGING_EXISTS;
    }

    int failed_recovery2_stagefd = openat(
        rootfd,
        kFailedRecovery2StagingName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    struct stat failed_recovery2_path_before;
    struct stat failed_recovery2_fd_before;
    if (failed_recovery2_stagefd < 0 ||
        fstatat(
            rootfd,
            kFailedRecovery2StagingName,
            &failed_recovery2_path_before,
            AT_SYMLINK_NOFOLLOW
        ) != 0 ||
        fstat(failed_recovery2_stagefd, &failed_recovery2_fd_before) != 0 ||
        failed_recovery2_path_before.st_dev !=
            failed_recovery2_fd_before.st_dev ||
        failed_recovery2_path_before.st_ino !=
            failed_recovery2_fd_before.st_ino ||
        !exact_failed_recovery2_staging(failed_recovery2_stagefd)) {
        if (failed_recovery2_stagefd >= 0) close(failed_recovery2_stagefd);
        close(historical_stagefd);
        close(rootfd);
        close(parentfd);
        return EXIT_STAGING_EXISTS;
    }
    int failed_recovery3_stagefd = openat(
        rootfd,
        kFailedRecovery3StagingName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    struct stat failed_recovery3_path_before;
    struct stat failed_recovery3_fd_before;
    if (failed_recovery3_stagefd < 0 ||
        fstatat(
            rootfd,
            kFailedRecovery3StagingName,
            &failed_recovery3_path_before,
            AT_SYMLINK_NOFOLLOW
        ) != 0 ||
        fstat(failed_recovery3_stagefd, &failed_recovery3_fd_before) != 0 ||
        failed_recovery3_path_before.st_dev !=
            failed_recovery3_fd_before.st_dev ||
        failed_recovery3_path_before.st_ino !=
            failed_recovery3_fd_before.st_ino ||
        !exact_failed_recovery3_staging(failed_recovery3_stagefd)) {
        if (failed_recovery3_stagefd >= 0) close(failed_recovery3_stagefd);
        close(failed_recovery2_stagefd);
        close(historical_stagefd);
        close(rootfd);
        close(parentfd);
        return EXIT_STAGING_EXISTS;
    }
    if (!absent_at(rootfd, kTargetName)) {
        close(failed_recovery3_stagefd);
        close(failed_recovery2_stagefd);
        close(historical_stagefd);
        close(rootfd);
        close(parentfd);
        return EXIT_TARGET_EXISTS;
    }
    if (!absent_at(rootfd, kStagingName)) {
        close(failed_recovery3_stagefd);
        close(failed_recovery2_stagefd);
        close(historical_stagefd);
        close(rootfd);
        close(parentfd);
        return EXIT_STAGING_EXISTS;
    }

    int primary_result = 0;
    int primary_errno = 0;
    int postcondition_result = 0;
    int postcondition_errno = 0;
    bool owner_write_window_open = false;
    bool promoted = false;
    bool staging_created = false;
    bool stage_root_sealed = false;
    ino_t staged_inode = 0;
    int stagefd = -1;
    errno = 0;
    if (fchmod(rootfd, kRootOwnerWriteMode) != 0) {
        primary_result = EXIT_ROOT_WINDOW;
        primary_errno = errno;
        goto finish;
    }
    owner_write_window_open = true;

    errno = 0;
    if (mkdirat(rootfd, kStagingName, 0700) != 0) {
        primary_result = EXIT_STAGING_CREATE;
        primary_errno = errno;
        goto finish;
    }
    staging_created = true;
    stagefd = openat(
        rootfd,
        kStagingName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    struct stat stage_metadata;
    if (stagefd < 0 ||
        !exact_staging_work_directory(stagefd) ||
        fstat(stagefd, &stage_metadata) != 0) {
        primary_result = EXIT_STAGING_CREATE;
        primary_errno = errno;
        goto finish;
    }
    staged_inode = stage_metadata.st_ino;
    errno = 0;
    if (!extract_and_verify(rootfd, stagefd)) {
        primary_result = EXIT_MATERIALIZE;
        primary_errno = errno;
        goto finish;
    }

    const unsigned flags =
        RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH;
    errno = 0;
    if (renameatx_np(
            rootfd,
            kStagingName,
            rootfd,
            kTargetName,
            flags
        ) != 0) {
        primary_result = EXIT_PROMOTE;
        primary_errno = errno;
        goto finish;
    }
    promoted = true;
    errno = 0;
    if (fchmod(stagefd, 0555) != 0) {
        primary_result = EXIT_PROMOTE;
        primary_errno = errno;
        goto finish;
    }
    errno = 0;
    if (fsync(stagefd) != 0) {
        primary_result = EXIT_PROMOTE;
        primary_errno = errno;
        goto finish;
    }
    if (!exact_sealed_full_release_tree(stagefd)) {
        primary_result = EXIT_PROMOTE;
        primary_errno = 0;
        goto finish;
    }
    errno = 0;
    if (fsync(rootfd) != 0) {
        primary_result = EXIT_PROMOTE;
        primary_errno = errno;
        goto finish;
    }
    stage_root_sealed = true;

finish:
    if (staging_created && !promoted && stagefd < 0) {
        stagefd = openat(
            rootfd,
            kStagingName,
            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        );
    }
    if (staging_created && !promoted && stagefd >= 0 && !stage_root_sealed) {
        errno = 0;
        if (fchmod(stagefd, 0555) != 0) {
            record_postcondition_failure(
                &postcondition_result,
                &postcondition_errno,
                EXIT_POSTCONDITION,
                errno
            );
        } else {
            errno = 0;
            if (fsync(stagefd) != 0) {
                record_postcondition_failure(
                    &postcondition_result,
                    &postcondition_errno,
                    EXIT_POSTCONDITION,
                    errno
                );
            } else if (!exact_release_entry(stagefd, 0555, true)) {
                record_postcondition_failure(
                    &postcondition_result,
                    &postcondition_errno,
                    EXIT_POSTCONDITION,
                    0
                );
            } else {
                stage_root_sealed = true;
            }
        }
    }
    if (owner_write_window_open) {
        errno = 0;
        if (fchmod(rootfd, kRootSealedMode) != 0) {
            record_postcondition_failure(
                &postcondition_result,
                &postcondition_errno,
                EXIT_ROOT_RESTORE,
                errno
            );
        }
    }
    struct stat root_after;
    struct stat path_after;
    char root_xattr_after[65];
    errno = 0;
    bool root_restored =
        fstat(rootfd, &root_after) == 0 &&
        fstatat(
            parentfd,
            kReleaseRootName,
            &path_after,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        exact_root_metadata(&root_after, kRootSealedMode) &&
        path_after.st_dev == root_metadata.st_dev &&
        path_after.st_ino == root_metadata.st_ino &&
        no_extended_acl(rootfd) &&
        exact_provenance_xattr_fingerprint(rootfd, root_xattr_after) &&
        strcmp(root_xattr_after, root_xattr_before) == 0;
    if (!root_restored) {
        record_postcondition_failure(
            &postcondition_result,
            &postcondition_errno,
            EXIT_ROOT_RESTORE,
            errno
        );
    }

    struct stat historical_path_after;
    struct stat historical_fd_after;
    errno = 0;
    bool historical_staging_unchanged =
        fstatat(
            rootfd,
            kHistoricalStagingName,
            &historical_path_after,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        fstat(historical_stagefd, &historical_fd_after) == 0 &&
        historical_path_after.st_dev == historical_path_before.st_dev &&
        historical_path_after.st_ino == historical_path_before.st_ino &&
        historical_fd_after.st_dev == historical_fd_before.st_dev &&
        historical_fd_after.st_ino == historical_fd_before.st_ino &&
        exact_historical_staging(historical_stagefd);
    if (!historical_staging_unchanged) {
        record_postcondition_failure(
            &postcondition_result,
            &postcondition_errno,
            EXIT_POSTCONDITION,
            errno
        );
    }

    struct stat failed_recovery2_path_after;
    struct stat failed_recovery2_fd_after;
    errno = 0;
    bool failed_recovery2_staging_unchanged =
        fstatat(
            rootfd,
            kFailedRecovery2StagingName,
            &failed_recovery2_path_after,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        fstat(failed_recovery2_stagefd, &failed_recovery2_fd_after) == 0 &&
        failed_recovery2_path_after.st_dev ==
            failed_recovery2_path_before.st_dev &&
        failed_recovery2_path_after.st_ino ==
            failed_recovery2_path_before.st_ino &&
        failed_recovery2_fd_after.st_dev ==
            failed_recovery2_fd_before.st_dev &&
        failed_recovery2_fd_after.st_ino ==
            failed_recovery2_fd_before.st_ino &&
        exact_failed_recovery2_staging(failed_recovery2_stagefd);
    if (!failed_recovery2_staging_unchanged) {
        record_postcondition_failure(
            &postcondition_result,
            &postcondition_errno,
            EXIT_POSTCONDITION,
            errno
        );
    }

    struct stat failed_recovery3_path_after;
    struct stat failed_recovery3_fd_after;
    errno = 0;
    bool failed_recovery3_staging_unchanged =
        fstatat(
            rootfd,
            kFailedRecovery3StagingName,
            &failed_recovery3_path_after,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        fstat(failed_recovery3_stagefd, &failed_recovery3_fd_after) == 0 &&
        failed_recovery3_path_after.st_dev ==
            failed_recovery3_path_before.st_dev &&
        failed_recovery3_path_after.st_ino ==
            failed_recovery3_path_before.st_ino &&
        failed_recovery3_fd_after.st_dev ==
            failed_recovery3_fd_before.st_dev &&
        failed_recovery3_fd_after.st_ino ==
            failed_recovery3_fd_before.st_ino &&
        exact_failed_recovery3_staging(failed_recovery3_stagefd);
    if (!failed_recovery3_staging_unchanged) {
        record_postcondition_failure(
            &postcondition_result,
            &postcondition_errno,
            EXIT_POSTCONDITION,
            errno
        );
    }

    if (primary_result == 0 && promoted) {
        int targetfd = openat(
            rootfd,
            kTargetName,
            O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        );
        struct stat target_metadata;
        bool target_valid =
            targetfd >= 0 &&
            fstat(targetfd, &target_metadata) == 0 &&
            target_metadata.st_ino == staged_inode &&
            exact_sealed_full_release_tree(targetfd) &&
            absent_at(rootfd, kStagingName);
        if (targetfd >= 0) close(targetfd);
        if (!target_valid) {
            record_postcondition_failure(
                &postcondition_result,
                &postcondition_errno,
                EXIT_POSTCONDITION,
                errno
            );
        }
    } else if (staging_created && !promoted) {
        struct stat failure_staging_path;
        struct stat failure_staging_fd;
        errno = 0;
        bool failure_staging_preserved =
            stagefd >= 0 &&
            fstatat(
                rootfd,
                kStagingName,
                &failure_staging_path,
                AT_SYMLINK_NOFOLLOW
            ) == 0 &&
            fstat(stagefd, &failure_staging_fd) == 0 &&
            failure_staging_path.st_dev == failure_staging_fd.st_dev &&
            failure_staging_path.st_ino == failure_staging_fd.st_ino &&
            failure_staging_fd.st_ino == staged_inode &&
            exact_release_entry(stagefd, 0555, true);
        if (!failure_staging_preserved) {
            record_postcondition_failure(
                &postcondition_result,
                &postcondition_errno,
                EXIT_POSTCONDITION,
                errno
            );
        }
    }
    fprintf(
        stderr,
        "primary_exit=%d primary_errno=%d "
        "postcondition_exit=%d postcondition_errno=%d\n",
        primary_result,
        primary_errno,
        postcondition_result,
        postcondition_errno
    );
    if (stagefd >= 0) close(stagefd);
    close(failed_recovery3_stagefd);
    close(failed_recovery2_stagefd);
    close(historical_stagefd);
    close(rootfd);
    close(parentfd);
    return final_exit_code(primary_result, postcondition_result);
}
