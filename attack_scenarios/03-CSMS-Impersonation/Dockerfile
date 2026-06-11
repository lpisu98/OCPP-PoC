FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install ocpp websockets

# Copy the attack script into the container
COPY csms_impersonation.py .

CMD [ "python3", "csms_impersonation.py" ]