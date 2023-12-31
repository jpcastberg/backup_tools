#!/usr/bin/env python
import json
import sys
import pathlib
import zipfile
import os
from glob import glob
from fnmatch import fnmatch
from datetime import datetime
from rclone_python import rclone


def matches_any_glob(string, glob_list):
    for pattern in glob_list:
        if fnmatch(string, pattern):
            return True
    return False


def list_absolute(directory, exclude):
    output_list = []
    full_exclude = []
    full_exclude += exclude
    full_exclude += global_exclude
    directory = os.path.normpath(directory)

    for filepath in pathlib.Path(directory).glob("*"):
        basename = os.path.basename(filepath)
        if not matches_any_glob(basename, full_exclude) and not filepath.is_symlink():
            output_list.append(str(filepath.absolute()))

    return output_list


def create_backup_zip(zip_filename: str, paths: list):
    print(f"🤐 Zipping directories to {backup_path}")
    with zipfile.ZipFile(zip_filename, "w") as zip_file:
        for path in paths:
            if os.path.isfile(path):
                add_to_zip_file(path, zip_file)
                continue
            for current_folder, subfolders, filenames in os.walk(path):
                for filename in filenames:
                    # if filename not in exclude_files:
                    file_path = os.path.join(current_folder, filename)
                    add_to_zip_file(file_path, zip_file)

    print("🤐✅ Zip complete")


def add_to_zip_file(file_path: str, zip_file: zipfile.ZipFile):
    if not os.access(file_path, os.R_OK):
        print(f"cant read {file_path}")
    if (
        os.path.exists(file_path)
        and os.access(file_path, os.R_OK)
        and not matches_any_glob(file_path, global_exclude)
        and file_path not in added_files
    ):
        zip_file.write(file_path)
        added_files.add(file_path)


def purge_old_backups():
    print("🔫😎 Looking for old backups to purge")
    old_backup_found = False
    existing_remote_backups = rclone.ls(f"{rclone_backup_type}:", args=rclone_args)

    for existing_remote_backup in existing_remote_backups:
        remote_backup_name = existing_remote_backup["Name"]
        remote_backup_date = datetime.strptime(remote_backup_name, "%Y-%m-%d")
        age = (now - remote_backup_date).days

        if age > int(max_backup_age_days):
            old_backup_found = True
            print(f"🏃 Purging remote backup: {remote_backup_name}")
            rclone.purge(f"{rclone_backup_type}:{remote_backup_name}", args=rclone_args)

    for local_backup in os.listdir(backup_dir_location):
        local_backup_date = datetime.strptime(
            str(local_backup).removesuffix(".zip"), "%Y-%m-%d"
        )
        age = (now - local_backup_date).days

        if age > int(max_backup_age_days) or local_backup_date == backup_name:
            old_backup_found = True
            print(f"🏃 Purging local backup: {local_backup}")
            os.remove(os.path.join(backup_dir_location, local_backup))

    if old_backup_found:
        print("🪦😎 Purge complete")
    else:
        print(
            f"No remote or local backups older than {max_backup_age_days} {day_pluralized} found"
        )


def build_include_list():
    include_list = []
    for file_config in files_to_backup:
        for include_path in file_config["include"]:
            file_paths = glob(include_path)
            for file_path in file_paths:
                if os.path.isdir(file_path):
                    include_list += list_absolute(
                        directory=include_path, exclude=file_config["exclude"]
                    )
                elif os.path.isfile(include_path):
                    include_list.append(include_path)
    return include_list


def backup_to_remote(backup_path, backup_name):
    print(f"⏫ Syncing {backup_path} as {rclone_backup_type}:{backup_name}")
    rclone.sync(
        backup_path,
        f"{rclone_backup_type}:{backup_name}",
        args=rclone_args,
    )
    print("🎉 Backup complete!")


# config_file schema:
# note: all paths support globs
# {
#     "backup_dir_location": "/path/to/backups",
#     "max_backup_age_days": 7,
#     "rclone_backup_type": "crypt",
#     "rclone_config_location": "/etc/rclone/rclone.conf",
#     "global_exclude": ["**/*.DS_Store", "**/home-assistant.log*", "**/node_modules/**"],
#     "files_to_backup": [
#         {
#             "include": ["/path/to/directory"],
#             "exclude": ["subdirectory_to_exclude", "file_to_exclude.txt"]
#         }
#     ]
# }

config_file = sys.argv[1]

with open(config_file, "r") as file:
    config = json.load(file)

now = datetime.now()
print(f"🟢 Starting backup at {now} using config: {config_file}")
global_exclude = config["global_exclude"]
backup_dir_location = config["backup_dir_location"]
list(global_exclude).append(backup_dir_location)
files_to_backup = config["files_to_backup"]
max_backup_age_days = config["max_backup_age_days"]
day_pluralized = "day" if max_backup_age_days == 1 else "days"
backup_name = now.strftime("%Y-%m-%d")
backup_path = os.path.join(backup_dir_location, f"{backup_name}.zip")
rclone_backup_type = config["rclone_backup_type"]
rclone_config_location = config["rclone_config_location"]
rclone_args = []
added_files = set()

if not rclone_config_location == "" and not rclone_config_location == None:
    rclone_args.append(f"--config={rclone_config_location}")


purge_old_backups()
include_list = build_include_list()
create_backup_zip(backup_path, include_list)
backup_to_remote(backup_path, backup_name)
