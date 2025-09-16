from collections import OrderedDict
from flask import Flask, render_template, request, jsonify
from jproperties import Properties
from types import ClassMethodDescriptorType
from typing import Any, NoReturn, Optional
from . import agent
from .agent import EmailContext, ValidationError

import re
import json
import logging
import os, signal
import sys
import traceback
import uuid
import asyncio
import requests

app = Flask(__name__)
ctxStr: str = ""
config = Properties()

# Get key
def getKey(
        keyString
) -> str:
    key = re.sub(r'\W+', '', keyString)
    return key.upper()

#
# Utility functions
#

# Signal handler for abnormal errors
def handler(signum, frame):
    signame= signal.Signals(signum).name
    app.logger.debug("Trapped signal %d", signum)
    sys.exit(1)

# Application property cache for key value pairs
def load_properties(propFile) -> bool:
    global config
    try:
        with open(propFile, "rb") as config_file:
            config.load(config_file)
            return True
    except Exception as err:
        app.logger.error("Exception fired - Cannot load %s", propFile)
        return False

#
# Interact with ADK
#
def process_query(query_data: dict) -> str:
    try:
        # Attempt to parse the query string as JSON
        try:
            app.logger.debug("Running query")
            # Validate the parsed JSON against the Pydantic schema
            app.logger.debug("Validating query")
            validated_data = EmailContext.model_validate(query_data)
            # Use the validated data to ensure a correctly formatted input is passed
            app.logger.debug("Running query")
            final_state_json = asyncio.run(agent.call_agent_async(json.dumps(validated_data.model_dump())))
        except (json.JSONDecodeError, ValidationError) as e:
            # If JSON parsing or validation fails, treat the input as a plain string
            app.logger.warning(f"Input is not a valid JSON for EmailContext. Processing as plain text. Error: {e}")
            final_state_json = asyncio.run(agent.call_agent_async(json.dumps(query_data)))
        
        return final_state_json
    except Exception as e:
        app.logger.error("Exception fired - Cannot process query")
        traceback.print_exc()
        return "Sorry, I don't understand that"

#
# Standard routines for handling URIs
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

    if load_properties("resources/app.properties"):
        # port = int(os.environ.get("PORT", 5000))
        port = int(config.get("port").data)
        isDebug = bool(config.get("debug").data == "true")
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
    else:
        sys.exit(1)
 