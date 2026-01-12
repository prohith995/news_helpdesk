#!/usr/bin/env python3
"""Run the News Intelligence Desk web interface."""

import uvicorn

if __name__ == "__main__":
    print("Starting News Intelligence Desk...")
    print("Open http://localhost:8000 in your browser")
    print()
    uvicorn.run(
        "newsdesk.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
