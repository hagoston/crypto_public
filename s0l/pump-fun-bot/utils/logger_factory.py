import os
import logging
import datetime

current_time = datetime.datetime.now()
formatted_time = current_time.strftime('%Y%m%d_%H%M%S')
os.makedirs('logs', exist_ok=True)
filename = f'logs/{formatted_time}.log'

def get_logger(name = 'logger', level = 'DEBUG'):
    DEBUG = os.environ.get("DEBUG", "false").lower() not in ["false", "no", "0"]

    logging.basicConfig(
        handlers=[
            logging.FileHandler(filename=filename, mode='a'),
            logging.StreamHandler()
        ],
        format = "[%(asctime)s] [%(name)13s] %(levelname)6s %(filename)s:%(lineno)d :: %(message)s",
        level = logging.DEBUG if DEBUG else logging.INFO
    )

    # disable specific module output
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logging.getLogger(name)