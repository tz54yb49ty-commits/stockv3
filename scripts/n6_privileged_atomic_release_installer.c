/*
 * N6 immutable Release privileged installer.
 *
 * This binary is deliberately not a general file mover.  A separately
 * attested runtime-control gate supplies the helper SHA-256 and authorizes
 * exactly one invocation.  It is not built or invoked by repository tests.
 */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#if !defined(__APPLE__)
#error "This helper is macOS-only; unsupported platforms fail closed."
#endif

#include <sys/attr.h>

#ifndef RENAME_EXCL
#error "renameatx_np RENAME_EXCL is required"
#endif
#ifndef RENAME_NOFOLLOW_ANY
#error "renameatx_np RENAME_NOFOLLOW_ANY is required"
#endif
#ifndef RENAME_RESOLVE_BENEATH
#error "renameatx_np RENAME_RESOLVE_BENEATH is required"
#endif

static const char kReleaseRoot[] =
    "/Users/chuanfuchen/.local/share/ashare-v3/releases/n6-b-track";

static bool is_safe_child_name(const char *name, bool staging) {
    const char *prefix = staging ? ".staging__" : "20";
    if (name == NULL || name[0] == '\0' || strchr(name, '/') != NULL ||
        strcmp(name, ".") == 0 || strcmp(name, "..") == 0) {
        return false;
    }
    return strncmp(name, prefix, strlen(prefix)) == 0;
}

static bool is_immutable_directory(const struct stat *st) {
    return S_ISDIR(st->st_mode) && (st->st_mode & 0777) == 0555 &&
           st->st_nlink >= 2;
}

int main(int argc, char *argv[]) {
    if (argc != 3 || geteuid() != 0 ||
        !is_safe_child_name(argv[1], true) ||
        !is_safe_child_name(argv[2], false)) {
        return 64;
    }

    int root_fd = open(kReleaseRoot, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (root_fd < 0) {
        return 65;
    }

    struct stat staging_stat;
    struct stat target_stat;
    if (fstatat(root_fd, argv[1], &staging_stat, AT_SYMLINK_NOFOLLOW) != 0 ||
        !is_immutable_directory(&staging_stat) ||
        fstatat(root_fd, argv[2], &target_stat, AT_SYMLINK_NOFOLLOW) == 0 ||
        errno != ENOENT) {
        close(root_fd);
        return 66;
    }

    const unsigned int flags =
        RENAME_EXCL | RENAME_NOFOLLOW_ANY | RENAME_RESOLVE_BENEATH;
    if (renameatx_np(root_fd, argv[1], root_fd, argv[2], flags) != 0) {
        close(root_fd);
        return 67;
    }

    if (fstatat(root_fd, argv[2], &target_stat, AT_SYMLINK_NOFOLLOW) != 0 ||
        !is_immutable_directory(&target_stat)) {
        close(root_fd);
        return 68;
    }
    close(root_fd);
    return 0;
}
