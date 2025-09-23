from collections import OrderedDict
from flask_cors import CORS
from flask import Flask, render_template, request, jsonify
from types import ClassMethodDescriptorType
from typing import Any, NoReturn, Optional

from . import agent
from .agent import EmailContext, ValidationError, call_agent_async
from . import utils
from .utils import load_properties, getValue

import json
import os, signal
import sys
import traceback
import uuid
import asyncio
import logging

app = Flask(__name__)
CORS(app)

#
# Utility functions
#

# Signal handler for abnormal errors
def handler(signum, frame):
    signame= signal.Signals(signum).name
    app.logger.debug("Trapped signal %d", signum)
    sys.exit(1)

#
# Interact with ADK
#
def process_query(query_data: dict) -> str:
    try:
        app.logger.debug("Running query")
        final_state_json = asyncio.run(call_agent_async(json.dumps(query_data), app.logger))
        return final_state_json
    except Exception as e:
        app.logger.error("Exception fired - Cannot process query")
        traceback.print_exc()
        return "Sorry, I don't understand that"

#
# Standard routines for handling URIs
#

# Version GET handler
@app.route("/version")
def version() -> Any:
    return jsonify({"version":"1.0"})

# Status GET probe handler
@app.route("/status")
def status() -> Any:
    return jsonify({"status":"live"})

# Chat POST handler
@app.route("/query", methods=["POST"])
def runquery():
    request_data = request.get_json()
    response_string = process_query(request_data["query"])
    response_data = json.loads(response_string)
    
    return jsonify({"response": response_data})

#
# Main routine
#
if __name__ == "__main__":
    signal.signal(signal.SIGBUS, handler)
    signal.signal(signal.SIGABRT, handler)
    signal.signal(signal.SIGILL, handler)
    signal.signal(signal.SIGTERM, handler)

    # Retrieve values using getValue from the utils module
    port_value = getValue("port")
    port = int(port_value) if port_value is not None else 5000
    
    debug_value = getValue("debug")
    isDebug = bool(debug_value == "true") if debug_value is not None else False

    if isDebug:
        logging.basicConfig(level=logging.DEBUG)
    app.logger.debug("Listening on port %d", port)

    # Check if the SSL certificate and key files exist
    if os.path.exists("cert.pem") and os.path.exists("key.pem"):
        ssl_context_tuple = ('cert.pem', 'key.pem')
        app.logger.info("SSL certificate files found. Starting with HTTPS support.")
    else:
        ssl_context_tuple = None
        app.logger.info("SSL certificate files not found. Starting with HTTP support.")
        
    app.run(debug=isDebug, host="0.0.0.0", port=port, ssl_context=ssl_context_tuple)
    
    sys.exit(0)