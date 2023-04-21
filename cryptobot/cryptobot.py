import argparse

from cryptostore import Cryptostore

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default='./config.yaml', help='path to the config file')
    args = parser.parse_args()

    print(args.config)
    cs = Cryptostore(config=args.config)
    try:
        cs.run()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()