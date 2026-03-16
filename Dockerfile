
# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user for security
RUN useradd -m botuser && chown -R botuser /app
USER botuser

# Make port 80 available to the world outside this container (Optional, if you add a web server later)
# EXPOSE 80

# Run main.py when the container launches
CMD ["python", "main.py"]
