# This Dockerfile builds the image for your Python bot.
# It will be used by docker-compose.

# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot script into the container
COPY slskd_discord_bot.py .

# Command to run the bot when the container starts
CMD ["python", "slskd_discord_bot.py"]
