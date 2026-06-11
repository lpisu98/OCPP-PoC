# OCPP Charge Point API

This project implements a FastAPI web application that simulates a charge point using the Open Charge Point Protocol (OCPP). The application allows users to interact with the charge point through HTTP requests, enabling actions such as starting and stopping transactions, sending notifications, and managing the charge point's state.

## Project Structure

```
ocpp-charge-point-api
├── src
│   ├── main.py               # Entry point of the FastAPI application
│   ├── charge_point.py       # ChargePoint class simulating charge point behavior
│   ├── api
│   │   ├── __init__.py       # Marks the api directory as a package
│   │   ├── routes.py         # Defines HTTP endpoints for the FastAPI application
│   │   └── schemas.py        # Pydantic models for request and response validation
│   ├── core
│   │   ├── __init__.py       # Marks the core directory as a package
│   │   ├── config.py         # Configuration settings for the application
│   │   └── logger.py         # Logging setup for the application
│   └── models
│       ├── __init__.py       # Marks the models directory as a package
│       └── transaction.py     # Data models related to transactions
├── requirements.txt           # Lists dependencies required for the project
├── .env                       # Environment variables for configuration
└── README.md                  # Documentation for the project
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd ocpp-charge-point-api
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables in the `.env` file as needed.

## Usage

To run the FastAPI application, execute the following command:

```
uvicorn src.main:app --reload
```

This will start the server at `http://127.0.0.1:8000`. You can access the API documentation at `http://127.0.0.1:8000/docs`.

## API Endpoints

- **POST /start-transaction**: Starts a new transaction.
- **POST /stop-transaction**: Stops an ongoing transaction.
- **GET /status**: Retrieves the current status of the charge point.
- **POST /reset**: Resets the charge point.
- **POST /change-configuration**: Changes configuration settings.
