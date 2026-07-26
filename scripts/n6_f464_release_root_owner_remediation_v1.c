/*
 * Exact, root-only, one-shot owner remediation for the F464 release root.
 *
 * This helper accepts zero arguments and changes only the directory owner UID
 * from 501 to 0. It has no recursive, chmod, shell, delete, service, plist,
 * database, runner, canary, or business-operation path.
 */
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/acl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/xattr.h>
#include <unistd.h>

static const char kReleaseParent[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases";
static const char kReleaseRootName[] = "n6-b-track";
static const char kReleaseRootPath[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track";
static const char kF464TargetName[] =
    "20260726_000001__f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kF464StagingName[] =
    ".staging__20260726_000001__"
    "f4641e9c4cd4dff1a817f779d28007fe7cdffe62";
static const char kF464InstallerPath[] =
    "/usr/local/libexec/ashare-v3/"
    "n6-f464-immutable-release-materializer-v2";
static const dev_t kExpectedDevice = (dev_t)16777232;
static const ino_t kExpectedInode = (ino_t)307341897;
static const uid_t kBeforeUid = (uid_t)501;
static const uid_t kAfterUid = (uid_t)0;
static const gid_t kExpectedGid = (gid_t)20;
static const mode_t kExpectedMode = (mode_t)0555;
static const char kExpectedXattrName[] = "com.apple.provenance";
static const char kExpectedXattrFingerprint[] =
    "9bd57bf16e9955726429cd301ee3dbf68c635f050f9317977592961193a494ea";

enum {
    EXIT_USAGE = 64,
    EXIT_NOT_ROOT = 65,
    EXIT_PRECONDITION = 66,
    EXIT_MUTATION = 67,
    EXIT_POSTCONDITION = 68
};

static void sha256_u64(CC_SHA256_CTX *context, uint64_t value) {
    unsigned char encoded[8];
    for (size_t index = 0; index < sizeof(encoded); ++index) {
        encoded[sizeof(encoded) - index - 1] =
            (unsigned char)(value & UINT64_C(0xff));
        value >>= 8;
    }
    CC_SHA256_Update(context, encoded, (CC_LONG)sizeof(encoded));
}

static int compare_names(const void *left, const void *right) {
    const char *const *a = left;
    const char *const *b = right;
    return strcmp(*a, *b);
}

static bool hex_digest(const unsigned char *digest, char output[65]) {
    static const char digits[] = "0123456789abcdef";
    for (size_t index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        output[index * 2] = digits[digest[index] >> 4];
        output[index * 2 + 1] = digits[digest[index] & 0x0f];
    }
    output[64] = '\0';
    return true;
}

static bool exact_xattr_fingerprint(int fd, char output[65]) {
    ssize_t names_size = flistxattr(fd, NULL, 0, 0);
    if (names_size <= 0) return false;
    char *names = malloc((size_t)names_size);
    if (names == NULL) return false;
    if (flistxattr(fd, names, (size_t)names_size, 0) != names_size) {
        free(names);
        return false;
    }

    size_t count = 0;
    for (ssize_t offset = 0; offset < names_size;) {
        size_t remaining = (size_t)(names_size - offset);
        size_t length = strnlen(names + offset, remaining);
        if (length == remaining) {
            free(names);
            return false;
        }
        ++count;
        offset += (ssize_t)length + 1;
    }
    if (count != 1 || strcmp(names, kExpectedXattrName) != 0) {
        free(names);
        return false;
    }

    char **ordered = calloc(count, sizeof(*ordered));
    if (ordered == NULL) {
        free(names);
        return false;
    }
    size_t index = 0;
    for (ssize_t offset = 0; offset < names_size;) {
        ordered[index++] = names + offset;
        offset += (ssize_t)strlen(names + offset) + 1;
    }
    qsort(ordered, count, sizeof(*ordered), compare_names);

    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    bool ok = true;
    for (index = 0; index < count && ok; ++index) {
        const char *name = ordered[index];
        size_t name_size = strlen(name);
        ssize_t value_size =
            fgetxattr(fd, name, NULL, 0, 0, 0);
        if (value_size < 0) {
            ok = false;
            break;
        }
        void *value = malloc((size_t)value_size == 0 ? 1 : (size_t)value_size);
        if (value == NULL ||
            fgetxattr(
                fd, name, value, (size_t)value_size, 0, 0
            ) != value_size) {
            free(value);
            ok = false;
            break;
        }
        sha256_u64(&context, (uint64_t)name_size);
        CC_SHA256_Update(&context, name, (CC_LONG)name_size);
        sha256_u64(&context, (uint64_t)value_size);
        CC_SHA256_Update(&context, value, (CC_LONG)value_size);
        free(value);
    }

    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    if (ok) {
        CC_SHA256_Final(digest, &context);
        hex_digest(digest, output);
    }
    free(ordered);
    free(names);
    return ok;
}

static bool no_extended_acl(int fd) {
    acl_t acl = acl_get_fd_np(fd, ACL_TYPE_EXTENDED);
    if (acl == NULL) return false;
    ssize_t length = 0;
    char *text = acl_to_text(acl, &length);
    bool ok = text != NULL && length == 0 && text[0] == '\0';
    if (text != NULL) acl_free(text);
    acl_free(acl);
    return ok;
}

static bool exact_metadata(
    const struct stat *metadata,
    uid_t expected_uid
) {
    return S_ISDIR(metadata->st_mode) &&
           metadata->st_dev == kExpectedDevice &&
           metadata->st_ino == kExpectedInode &&
           metadata->st_uid == expected_uid &&
           metadata->st_gid == kExpectedGid &&
           (metadata->st_mode & 07777) == kExpectedMode;
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

int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1) return EXIT_USAGE;
    if (getuid() != 0 || geteuid() != 0) return EXIT_NOT_ROOT;

    int parent_fd =
        open(kReleaseParent, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (parent_fd < 0) return EXIT_PRECONDITION;
    int root_fd = openat(
        parent_fd,
        kReleaseRootName,
        O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    );
    if (root_fd < 0) {
        close(parent_fd);
        return EXIT_PRECONDITION;
    }

    char resolved_path[1024];
    struct stat path_metadata;
    struct stat before;
    char xattr_before[65];
    bool valid_before =
        fcntl(root_fd, F_GETPATH, resolved_path) == 0 &&
        strcmp(resolved_path, kReleaseRootPath) == 0 &&
        fstatat(
            parent_fd,
            kReleaseRootName,
            &path_metadata,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        fstat(root_fd, &before) == 0 &&
        path_metadata.st_dev == before.st_dev &&
        path_metadata.st_ino == before.st_ino &&
        exact_metadata(&before, kBeforeUid) &&
        no_extended_acl(root_fd) &&
        exact_xattr_fingerprint(root_fd, xattr_before) &&
        strcmp(xattr_before, kExpectedXattrFingerprint) == 0 &&
        absent_at(root_fd, kF464TargetName) &&
        absent_at(root_fd, kF464StagingName) &&
        absolute_path_absent(kF464InstallerPath);
    if (!valid_before) {
        close(root_fd);
        close(parent_fd);
        return EXIT_PRECONDITION;
    }

    if (fchown(root_fd, kAfterUid, (gid_t)-1) != 0) {
        close(root_fd);
        close(parent_fd);
        return EXIT_MUTATION;
    }

    struct stat after;
    struct stat path_after;
    char xattr_after[65];
    bool valid_after =
        fstat(root_fd, &after) == 0 &&
        fstatat(
            parent_fd,
            kReleaseRootName,
            &path_after,
            AT_SYMLINK_NOFOLLOW
        ) == 0 &&
        exact_metadata(&after, kAfterUid) &&
        path_after.st_dev == before.st_dev &&
        path_after.st_ino == before.st_ino &&
        after.st_dev == before.st_dev &&
        after.st_ino == before.st_ino &&
        after.st_gid == before.st_gid &&
        (after.st_mode & 07777) == (before.st_mode & 07777) &&
        no_extended_acl(root_fd) &&
        exact_xattr_fingerprint(root_fd, xattr_after) &&
        strcmp(xattr_after, xattr_before) == 0 &&
        absent_at(root_fd, kF464TargetName) &&
        absent_at(root_fd, kF464StagingName) &&
        absolute_path_absent(kF464InstallerPath);

    close(root_fd);
    close(parent_fd);
    return valid_after ? 0 : EXIT_POSTCONDITION;
}
