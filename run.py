from app import create_app

app = create_app()

if __name__ == '__main__':
    # debug=True 适合开发，生产环境请禁用
    app.run(host='127.0.0.1', port=5000, debug=True)