import tarfile
import gzip
import os
import shutil
import multiprocessing as mp
import re


def unziptar(tarfile_and_opath):
    """worker unzips one file"""
    fullpath = tarfile_and_opath[0]
    output_dir = tarfile_and_opath[1]
    print('extracting... ', fullpath)
    tar = tarfile.open(fullpath, 'r:gz')
    tar.extractall(os.path.dirname(output_dir))
    tar.close()


def fanout_unziptar(in_path, out_path, ffilter):
    # T_DEPTH files untar in 2 loops, first loop into temporary folder
    tmp_dir = '__TMP__/'
    in_paths = [in_path, out_path+'/'+tmp_dir]

    for ipath in in_paths:
        files_2_untar = []

        filter = ffilter
        if not ffilter or tmp_dir in ipath:
            filter = '[A-Z].*tar.gz'
        for root, _, files in os.walk(ipath):
            # ADAUSDT.*202204.*tar.gz
            filtered_files = re.findall(filter, '\n'.join(files))

            for i in filtered_files:
                tarfile = os.path.join(root, i)
                basename = os.path.basename(tarfile)
                symbol = basename.split('_')[0]

                if 'T_TRADE' in basename:
                    # T_TRADEs in one round
                    op = out_path+'/'+symbol+'/T_TRADE/'
                elif tmp_dir in tarfile and 'T_DEPTH' in basename:
                    # final untar from temporary folder
                    op = out_path+'/'+symbol+'/T_DEPTH/'
                elif 'T_DEPTH' in basename:
                    # untar to temporary folder for T_DEPTHs
                    op = out_path+'/'+tmp_dir+'/'

                os.makedirs(op, exist_ok=True)
                files_2_untar.append([os.path.join(root, i), op])

            break  # non recursive

        if files_2_untar:
            pool = mp.Pool(min(mp.cpu_count(), len(files_2_untar)))  # number of workers
            pool.map(unziptar, files_2_untar, chunksize=1)
            pool.close()

    # remove temporary dir
    if os.path.isdir(out_path+'/'+tmp_dir):
        shutil.rmtree(out_path+'/'+tmp_dir) 


if __name__ == "__main__":

    # python3 untar_data.py --input_path ../../crypto/data/binance_targz --output_path ../../crypto/data/binance_uncompressed --filter ADAUSDT.*202204.*tar.gz
    import argparse
    parser = argparse.ArgumentParser(description='unzipper')
    parser.add_argument('--input_path', required=True, help='folder path of tar.gz files')
    parser.add_argument('--output_path', required=True, help='output directory')
    parser.add_argument('--filter', required=False, default='', help='file filter')
    args = parser.parse_args()
    
    fanout_unziptar(args.input_path, args.output_path, args.filter)

    print('tar.gz extraction has completed')
