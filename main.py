
from app import app

if __name__ == "__main__":
    # Use 0.0.0.0 to make the server publicly accessible
    app.run(host="0.0.0.0", port=5000)
