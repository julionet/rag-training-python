import uvicorn

from src import config
from src.api import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host=config.API_HOST, port=config.API_PORT)
