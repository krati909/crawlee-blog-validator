# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------
# Why Docker instead of a zip + Lambda Layer?
#
#   Playwright requires Chromium (~170 MB).  Combined with Python
#   dependencies, the total exceeds Lambda's 250 MB unzipped limit for
#   zip-based deployments.  Docker-based Lambda functions support images
#   up to 10 GB, giving us all the headroom we need.
#
# Base image:
#   AWS provides python3.12 Lambda base images that are pre-configured with
#   the Lambda Runtime Interface Client (RIC).  Using the official image
#   avoids having to install and configure the RIC manually.
#
# Build:
#   docker build -t crawlee-blog-validator .
#
# Local smoke-test:
#   docker run --rm -p 9000:8080 crawlee-blog-validator
#   curl -XPOST http://localhost:9000/2015-03-31/functions/function/invocations \
#        -d '{}'
# ---------------------------------------------------------------------------

FROM public.ecr.aws/lambda/python:3.12

# ---------------------------------------------------------------------------
# System dependencies required by Playwright / Chromium
# ---------------------------------------------------------------------------
RUN dnf install -y \
    atk \
    at-spi2-atk \
    cups-libs \
    dbus-glib \
    gtk3 \
    libdrm \
    libgbm \
    libxkbcommon \
    mesa-libgbm \
    nss \
    xorg-x11-server-Xvfb \
    && dnf clean all

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Install Playwright browsers
# ---------------------------------------------------------------------------
# PLAYWRIGHT_BROWSERS_PATH tells Playwright where to install / find browsers.
# We put it inside the container so it's baked into the image.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
COPY config/       ${LAMBDA_TASK_ROOT}/config/
COPY src/          ${LAMBDA_TASK_ROOT}/src/
COPY orchestrator.py   ${LAMBDA_TASK_ROOT}/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/

# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------
CMD ["lambda_handler.lambda_handler"]
