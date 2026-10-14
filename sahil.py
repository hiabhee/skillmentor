from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Hello HTTPS!"

app.run(
    ssl_context=(r"localhost.crt", r"localhost.key")
)


