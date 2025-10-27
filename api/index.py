from app import app

# Vercel precisa que a aplicação seja exportada em api/
if __name__ == "__main__":
    app.run()