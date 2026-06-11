FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port for the charge point
EXPOSE 9000

# Start the charge point application with Uvicorn
CMD ["uvicorn", "src.charge_point:app", "--host", "0.0.0.0", "--port", "9000"]