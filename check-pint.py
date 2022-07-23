#!/usr/bin/env python3
#check-pint.py v2.0.

from pathlib import Path
import argparse, copy, csv, hashlib, os, sys, subprocess
from multiprocessing import Pool
from itertools import repeat
from PIL import Image

PINT_FILENAME = ".pint.txt"
#MAGICK_CMD = '/usr/bin/identify'
PROCESS_COUNT = 4

BLACK = '\033[0;30m' # Black
RED = '\033[0;31m' # Red
GREEN = '\033[0;32m' # Green
YELLOW = '\033[0;33m' # Yellow
BLUE = '\033[0;34m' # Blue
PURPLE = '\033[0;35m' # Purple
CYAN = '\033[0;36m' # Cyan
WHITE = '\033[0;37m' # White
NC = '\033[0m' # No Color

pint_input = {}
pint_output = {}
mode = str()

#Process command-line arguments/options into variables
#Returns an argparse class namespace object
def argparser():
    parser = argparse.ArgumentParser(description='Compare file/dir(s) against previous integrity checks.')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='verbose output')
    parser.add_argument('path', type=lambda p: Path(p).resolve(),
                        help='path to the file or folder')
    parser.add_argument('-u', '--update', dest='update', action='store_true', default=False,
                        help='update the pint file with all calculated/changed hashes')
    parser.add_argument('-n', '--new-only', dest='new', action='store_true', default=False,
                        help='process/add new files ONLY, (ie. NO verification of existing checksums will be performed)')
    parser.add_argument('-r', '--recursive', dest='recursive', action='store_true', default=False,
                        help='recursive')
    #parser.add_argument('source', metavar='SOURCE', type=str, help='Local directory (tree) to upload')
    #parser.add_argument('dest', metavar='DEST', type=str, help='Full path to SmugMug destination node')

    return parser.parse_args()

#Given an argparse class namespace object,
#Validate arguments/options,
#Exits on errors
def validate_args(args):
    global mode
    #confirm given path is a file or directory
    if Path.is_dir(args.path): mode = 'directory'
    elif Path.is_file(args.path): mode = 'file'
    else:
        print(f"Path, {args.path}, needs to be an existing file or directory", file=sys.stderr)
        sys.exit(1)
    #Error if a directory is not given with new-only flag
    if args.new and not args.path.is_dir:
        print(f"Path, {args.path}, must be a directory when using --new-only (-n)")
        sys.exit(2)
    #Error if a directory is not given with recursive flag
    if args.recursive and not args.path.is_dir:
        print(f"Path, {args.path}, must be a directory when using --recursive (-r)")
        sys.exit(3)

#Given a path (of either a file or directory)
#return the full path of the expected pint file
def get_pint_path(given_path):
    pint_path = None
    full_path = Path(given_path).resolve()
    if full_path.is_dir():
        pint_path = full_path/PINT_FILENAME
    elif full_path.is_file():
        folder = full_path.parent
        pint_path = folder/PINT_FILENAME

    return pint_path

#Given a path,
#read in and return dictionary of the pint data
#csv file format (filename,filehash,pixelhash)
#pint_data={'filename1': {'filehash': '817751a876d97g6fe', 'pixelhash': '98861fadge9789ab9cd'}, ...}
def import_pint(given_path, verbose, recursive):
    #TODO account for blank lines
    pint_path = None
    full_path = Path(given_path).resolve()
    if full_path.is_dir():
        pint_path = full_path/PINT_FILENAME
    elif full_path.is_file():
        folder = full_path.parent
        pint_path = folder/PINT_FILENAME
    file = pint_path

    pint_data = {}
    if Path(file).is_file():
        with open(file, newline='') as csvfile:
            pint_reader = csv.reader(csvfile, delimiter=',')
            next(pint_reader)
            for row in pint_reader:
                col1, col2, col3 = row
                pint_data[col1] = {'filehash': col2, 'pixelhash': col3}
                filehash = {col1: col2}
                pixelhash = {col1: col3}
        #for k,v in pint_data.items():
        #    print(k, v)
            if verbose: print(pint_data)
        return pint_data
    else:
        if verbose: print(f"No pint file found at {file}")
        return pint_data

#Given the pint filepath,
#write the file (with data from the global output dictionary) and return status
#csv file format (filename,filehash,pixelhash)
#pint_data={'filename1': {'filehash': '817751a876d97g6fe', 'pixelhash': '98861fadge9789ab9cd'}, ...}
def export_pint(file):
    global pint_output
    with open(file, 'w', newline='') as csvfile:
        pint_writer = csv.writer(csvfile, delimiter=',', lineterminator='\n')
        header = ('filename','filehash','pixelhash')
        pint_writer.writerow(header)
        for key in sorted(pint_output):
            row = (key,pint_output[key]['filehash'],pint_output[key]['pixelhash'])
            pint_writer.writerow(row)
    #TODO add return false for failed file writing
    return True

#Given a directory and filename, return filehash
def calculate_file_hash(directory, file, block_size=1024*128):
    '''
    Block size directly depends on the block size of your filesystem
    to avoid performances issues
    '''
    path = directory + '/' + file
    h = hashlib.md5(usedforsecurity=False)
    try:
        with open(path,'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                h.update(chunk)
    except IOError as e:
        print("I/O error({0}): {1}".format(e.errno, e.strerror), file=sys.stderr)
        raise

    return h.hexdigest()

#Given a directory and filename, return pixelhash
def calculate_pixel_hash(directory, file):
    path = directory + '/' + file
    h = hashlib.md5(usedforsecurity=False)
    #cmd_result = subprocess.run([MAGICK_CMD, "-format", '%#', path], capture_output=True, text=True)

    h.update(Image.open(path).tobytes())
    #Image.Image.close(path)
    #print(cmd_result.hexdigest())
    return h.hexdigest()
    #return cmd_result.stdout

# Given a directory,
# return a dictionary of jpg's in the directory
def get_image_dict(directory):
    image_list = []
    image_list =  sorted(Path(directory).glob('*.jpg'))
    string_list = map(lambda p: Path(p).name, image_list)
    image_dict = dict.fromkeys(string_list)
    #print(image_dict)

    return image_dict

# Given a directory path and dictionary of filenames,
# add filehashes to dictionary
# return_dict={filename1: {'filehash': '65a6d75f6ae4d548', ...}, ...}
def add_file_hashes(directory, working_dict, verbose):

    keylist = list(working_dict.keys())
    if verbose: print('calculating file checksums')
    with Pool(PROCESS_COUNT) as p:
        results = p.starmap(calculate_file_hash, list(zip(repeat(directory), keylist)))
    # for i in range(len(keylist)):
    #     print(keylist[i],results[i])

    for key, value in working_dict.items():
        idx = ''
        idx = keylist.index(key)
        if value:
            working_dict[key].update({'filehash': results[idx]})
        else:
            working_dict[key] = {'filehash': results[idx]}
        #working_dict[key] = {'filehash': filehash}
    return

#Given a directory path and dictionary of filenames,
#add pixelhashes to dictionary
# return_dict={filename1: {'pixelhash': '65a6d75f6ae4d548', ...}, ...}
def add_pixel_hashes(directory, working_dict, keylist=False):

    #if args.verbose: print('calculating pixel checksums')
    if not keylist:
        keylist = list(working_dict.keys())
    # if verbose: print('calculating pixel checksums')
    with Pool(PROCESS_COUNT) as p:
        results = p.starmap(calculate_pixel_hash, list(zip(repeat(directory), keylist)))
    # for i in range(len(keylist)):
    #     print(keylist[i],results[i])
    for key in keylist:
        idx = ''
        idx = keylist.index(key)
        if working_dict[key]:
            working_dict[key].update({'pixelhash': results[idx]})
        else:
            working_dict[key] = {'pixelhash': results[idx]}

    # if list:
    #     for file in list:
    #         pixhash = ''
    #         pixhash = calculate_pixel_hash(directory, file)
    #         #working_dict.update({key: {'pixelhash': pixhash}})
    #         working_dict[file].update({'pixelhash': pixhash})
    # else:
    #     for file in working_dict:
    #         pixhash = ''
    #         pixhash = calculate_pixel_hash(directory, file)
    #         #working_dict.update({key: {'pixelhash': pixhash}})
    #         working_dict[file].update({'pixelhash': pixhash})
    return

#Given a dictionary of filenames and filehashes,
#add a flag (comparison result) to the dictionary
def flag_filehash_changes(working_dict):
    global pint_input
    for key in working_dict:
        if key in pint_input:
            if working_dict[key]['filehash'] == pint_input[key]['filehash']:
                working_dict[key].update({'flag': 'IDENTICAL'})
            else:
                working_dict[key].update({'flag': 'CHANGED'})
        else:
            working_dict[key].update({'flag': 'NEW'})
    return

#Given a dictionary of filenames and pixelhashes,
#modify the flag (comparison result) in the dictionary
def flag_pixel_meta_changes(working_dict):
    global pint_input
    global pint_output
    for key in working_dict:
        if working_dict[key]['flag'] == 'CHANGED':
            if working_dict[key]['pixelhash'] == pint_input[key]['pixelhash']:
                working_dict[key].update({'flag': 'CHANGED (METADATA)'})
                # if update:
                #     pint_output[key].update({'filehash': working_dict[key]['filehash']})
            else:
                working_dict[key].update({'flag': 'CHANGED (PIXELDATA)'})
                # if update:
                #     pint_output[key].update({'pixelhash': working_dict[key]['pixelhash']})
    return

#Given a dictionary of existing filenames,
#return a dictionary of missing files
def create_missing_files_dict(working_dict):
    global pint_input
    missing_dict = {}
    for key in pint_input:
        if not key in working_dict:
            missing_dict[key] = {'flag': 'MISSING'}
    return missing_dict

#Given a dictionary of existing filenames,
#return a dictionary of new files (not listed in current pint file)
def create_new_files_dict(working_dict):
    global pint_input
    new_dict = {}
    for key in working_dict:
        if not key in pint_input:
            new_dict[key] = {'flag': 'NEW'}
    return new_dict

#given a diretory
#backup existing pint file for given directory, and write an updated pint file
def update_pint_file(directory):
    global pint_output
    pint_file = str(get_pint_path(directory))
    backup_file = pint_file + '.bak'
    new_file = pint_file + '.new'
    export_pint(new_file)
    if export_pint:
        if Path(pint_file).is_file():
            os.replace(pint_file, backup_file)
        os.rename(new_file, pint_file)
    return


def prep_file_output_data(working_dict, missing_dict=None):
    global pint_output
    for key in working_dict:
        if working_dict[key]['flag'] == 'NEW':
            pint_output[key] = {'filehash': working_dict[key]['filehash'], 'pixelhash': working_dict[key]['pixelhash']}
        elif working_dict[key]['flag'] == 'CHANGED (METADATA)':
            pint_output[key].update({'filehash': working_dict[key]['filehash']})
        elif working_dict[key]['flag'] == 'CHANGED (PIXELDATA)':
            pint_output[key].update({'filehash': working_dict[key]['filehash']})
            pint_output[key].update({'pixelhash': working_dict[key]['pixelhash']})

    if missing_dict:
        for key in missing_dict:
            pint_output.pop(key, None)

    return

# def fast_scandir(dirname):
#     subfolders= [f.path for f in os.scandir(dirname) if f.is_dir()]
#     for dirname in list(subfolders):
#         subfolders.extend(fast_scandir(dirname))
#     return subfolders

def check_single_image(directory, filename, verbose, update):
    global pint_input
    global pint_output
    #calculate filehash
    #directory = str(Path(args.path)).rsplit('/', 1)[0]
    #filename = Path(args.path).name
    filehash = calculate_file_hash(directory, filename)
    live_dict = {filename: None}

    add_file_hashes(directory, live_dict, verbose)
    flag_filehash_changes(live_dict)

    #calculate and add pixelhashes to changed files
    changed_files_list = []
    for key in live_dict:
        if live_dict[key]['flag'] == 'CHANGED':
            changed_files_list.append(key)
    add_pixel_hashes(directory, live_dict, changed_files_list)

    #calculate and add pixelhashes to new files
    new_files_list = []
    for key in live_dict:
        if live_dict[key]['flag'] == 'NEW':
            new_files_list.append(key)
    add_pixel_hashes(directory, live_dict, new_files_list)

    #determine whether metadata or pixeldata changed
    #and flag accordingly
    flag_pixel_meta_changes(live_dict)

    for key in sorted(live_dict):
        if live_dict[key]['flag'] == 'IDENTICAL':
            print(f"{key} IDENTICAL")
        elif live_dict[key]['flag'] == 'CHANGED (METADATA)':
            print(f"{key} {YELLOW}CHANGED (METADATA){NC}")
        elif live_dict[key]['flag'] == 'CHANGED (PIXELDATA)':
            print(f"{key} {RED}CHANGED (PIXELDATA){NC}")
        elif live_dict[key]['flag'] == 'NEW':
            print(f"{key} {GREEN}NEW{NC}")
        elif live_dict[key]['flag'] == 'MISSING':
            print(f"{key} {YELLOW}MISSING{NC}")

    if update:
        prep_file_output_data(live_dict)
        update_pint_file(directory)

def check_directory(path, verbose, update):
    sys.exit(12)

def main():
    global pint_input
    global pint_output
    global mode
    args = argparser()
    validate_args(args)

    #If -n option was given
    #only add new images to pint file then exit
    #(useful for daily cronjob to pick up newly downloaded images)
    if args.new:
        if args.recursive:
            d = sorted(args.path.glob('**/'))
        else:
            d = [args.path]
        for subdir in d:
            #print(pint_input)
            pint_input = import_pint(subdir, args.verbose, args.recursive)
            #print(pint_input)
            pint_output = copy.deepcopy(pint_input)
            directory = str(subdir)
            live_dict = get_image_dict(directory)
            new_files_dict = create_new_files_dict(live_dict)
            if new_files_dict:
                add_file_hashes(directory, new_files_dict, args.verbose)
                add_pixel_hashes(directory, new_files_dict)
                pint_output |= new_files_dict
                update_pint_file(directory)
                print(f"New files found in {directory}, added to pint file")
            #     sys.exit(0)
            # else:
            #     sys.exit(0)
        sys.exit(0)
    #Given a file on the command-line...
    if mode == 'file':
        pint_input = import_pint(args.path, args.verbose, args.recursive)
        if args.update:
            pint_output = copy.deepcopy(pint_input)
        #directory = str(args.path).rsplit('/', 1)[0]
        directory = str(args.path.parent)
        #print(directory)
        filename = args.path.name
        check_single_image(directory, filename, args.verbose, args.update)

    #Given a directory on the command-line...
    elif mode == 'directory':
        if args.recursive:
            d = sorted(args.path.glob('**/'))
        else:
            d = [args.path]
        for cwd in d:
            #print(subdir)
            pint_input = import_pint(cwd, args.verbose, args.recursive)
            if args.update:
                pint_output = copy.deepcopy(pint_input)

            directory = str(cwd)
            live_dict = get_image_dict(directory)
            missing_files_dict = create_missing_files_dict(live_dict)

            if live_dict:
                add_file_hashes(directory, live_dict, args.verbose)
                flag_filehash_changes(live_dict)

                #calculate and add pixelhashes to changed files
                changed_files_list = []
                for key in live_dict:
                    if live_dict[key]['flag'] == 'CHANGED':
                        changed_files_list.append(key)
                add_pixel_hashes(directory, live_dict, changed_files_list)

                #calculate and add pixelhashes to new files
                new_files_list = []
                for key in live_dict:
                    if live_dict[key]['flag'] == 'NEW':
                        new_files_list.append(key)
                add_pixel_hashes(directory, live_dict, new_files_list)

                #determine whether metadata or pixeldata changed
                #and flag accordingly
                flag_pixel_meta_changes(live_dict)

                #combine the live filesystem and missing_files dicts for print output
                combined_dict = {}
                combined_dict = live_dict | missing_files_dict

                for key in sorted(combined_dict):
                    if combined_dict[key]['flag'] == 'IDENTICAL':
                        print(f"{key} IDENTICAL")
                    elif combined_dict[key]['flag'] == 'CHANGED (METADATA)':
                        print(f"{key} {YELLOW}CHANGED (METADATA){NC}")
                    elif combined_dict[key]['flag'] == 'CHANGED (PIXELDATA)':
                        print(f"{key} {RED}CHANGED (PIXELDATA){NC}")
                    elif combined_dict[key]['flag'] == 'NEW':
                        print(f"{key} {GREEN}NEW{NC}")
                    elif combined_dict[key]['flag'] == 'MISSING':
                        print(f"{key} {YELLOW}MISSING{NC}")

                if args.update:
                    #remove missing files from new output file
                    prep_file_output_data(live_dict, missing_files_dict)
                    update_pint_file(directory)
                    # for key in sorted(pint_output):
                    #     print(f"{key} {pint_output[key]['filehash']} {pint_output[key]['pixelhash']}")


if __name__ == '__main__':
    main()
