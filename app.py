from threading import Lock
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

deliveries_db = {}
next_id = 1
db_lock = Lock()

VALID_STATUSES = ["created", "in_transit", "delivered"]


# ----------------------------------------------------
# Exception Handlers לחוזה א4 + א5 (חובה להחזיר "error")
# ----------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request body or parameters"}
    )


# ----------------------------------------------------
# Endpoints
# ----------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/deliveries", status_code=status.HTTP_201_CREATED)
async def create_delivery(request: Request):
    global next_id

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON or missing body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    recipient = body.get("recipient")
    address = body.get("address")

    if not isinstance(recipient, str) or not recipient.strip():
        raise HTTPException(status_code=400, detail="Recipient must be a non-empty string")
    if not isinstance(address, str) or not address.strip():
        raise HTTPException(status_code=400, detail="Address must be a non-empty string")

    with db_lock:
        delivery_id = next_id
        next_id += 1
        delivery = {
            "id": delivery_id,
            "recipient": recipient,
            "address": address,
            "status": "created"
        }
        deliveries_db[delivery_id] = delivery

    return delivery


@app.get("/deliveries")
def get_deliveries(status: Optional[str] = None):
    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        return [d for d in deliveries_db.values() if d["status"] == status]

    return list(deliveries_db.values())


@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int):
    if delivery_id not in deliveries_db:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return deliveries_db[delivery_id]


@app.patch("/deliveries/{delivery_id}/status")
async def update_delivery_status(delivery_id: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict) or "status" not in body:
        raise HTTPException(status_code=400, detail="Missing status field")

    new_status = body.get("status")

    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status value")

    with db_lock:
        if delivery_id not in deliveries_db:
            raise HTTPException(status_code=404, detail="Delivery not found")

        current_status = deliveries_db[delivery_id]["status"]

        if current_status == "created" and new_status == "in_transit":
            deliveries_db[delivery_id]["status"] = new_status
        elif current_status == "in_transit" and new_status == "delivered":
            deliveries_db[delivery_id]["status"] = new_status
        else:
            raise HTTPException(status_code=409, detail="Invalid status transition")

        return deliveries_db[delivery_id]


@app.delete("/deliveries/{delivery_id}")
def delete_delivery(delivery_id: int):
    with db_lock:
        if delivery_id not in deliveries_db:
            raise HTTPException(status_code=404, detail="Delivery not found")

        if deliveries_db[delivery_id]["status"] != "created":
            raise HTTPException(
                status_code=409,
                detail="Cannot delete delivery that is in_transit or delivered"
            )

        del deliveries_db[delivery_id]

    return Response(status_code=status.HTTP_204_NO_CONTENT)