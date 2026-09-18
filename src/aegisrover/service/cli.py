import uvicorn

def main():
    uvicorn.run('aegisrover.service.api:app', host='127.0.0.1', port=8088)
if __name__ == '__main__':
    main()
