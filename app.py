from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel

from real_estate_pipeline import Action, RealEstatePipelineEnv
from real_estate_pipeline.cab_booking import book_cab, list_cab_providers, preview_cab_booking
from real_estate_pipeline.graders import grade_task
from real_estate_pipeline.live_simulator import (
    DEFAULT_LIVE_LEADS,
    DEFAULT_STREAM_LEADS,
    process_live_lead,
    simulate_live_traffic,
    stream_live_traffic_events,
)
from real_estate_pipeline.models import InboundLead, LiveTrafficSimulationRequest, LiveTrafficSimulationResponse
from real_estate_pipeline.tasks import load_task


app = FastAPI(title="Real Estate Pipeline OpenEnv", version="0.1.0")
env = RealEstatePipelineEnv()
latest_call_cache: dict[str, object] = {}
conversion_metrics: dict[str, dict[str, int]] = {
    "residential": {
        "total_leads": 0,
        "contacted": 0,
        "interested_in_visit": 0,
        "appointment_scheduled": 0,
        "deal_closed": 0,
    },
    "commercial": {
        "total_leads": 0,
        "contacted": 0,
        "proposal_sent": 0,
        "negotiation": 0,
        "deal_closed": 0,
    },
}

# Lead categorization for current stream
lead_categorization: dict[str, list[dict[str, object]]] = {
    "eligible_for_contact": [],
    "scheduled_for_visit": [],
    "cold_leads": [],
    "qualification_pending": [],
    "deal_closed": [],
}

# Market rate data structure - tracks property prices by location
market_rates: dict[str, dict[str, list[dict[str, object]]]] = {
    "Whitefield": {
        "2bhk apartment": [
            {"price": 9200000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "3bhk apartment": [
            {"price": 10500000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "4bhk apartment": [
            {"price": 13200000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "plot": [
            {"price": 8000000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
    },
    "Sarjapur": {
        "2bhk apartment": [
            {"price": 8500000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "3bhk apartment": [
            {"price": 11800000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "4bhk apartment": [
            {"price": 14500000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "plot": [
            {"price": 7200000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
    },
    "Marathahalli": {
        "2bhk apartment": [
            {"price": 9000000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "3bhk apartment": [
            {"price": 10200000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "4bhk apartment": [
            {"price": 13000000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "plot": [
            {"price": 7800000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
    },
    "Indiranagar": {
        "2bhk apartment": [
            {"price": 10200000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "3bhk apartment": [
            {"price": 12300000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "4bhk apartment": [
            {"price": 15500000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "plot": [
            {"price": 9500000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
    },
    "CBD Retail District": {
        "retail": [
            {"price": 315000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
        "office": [
            {"price": 280000, "timestamp": datetime.now(timezone.utc).isoformat()},
        ],
    },
}


class ResetRequest(BaseModel):
    task_id: str | None = None


class CabBookingRequest(BaseModel):
    provider: str
    pickup_location: str
    drop_location: str
    rider_name: str
    mode: str = "auto"


class CabEligibilityMockRequest(BaseModel):
    customer_name: str
    inquiry: str
    customer_location: str
    property_location: str
    property_type: str = "2BHK apartment"
    budget: int | None = None
    timeline_days: int | None = None
    profession: str | None = None
    employment_type: str | None = None
    total_experience_years: int | None = None
    provider: str = "uber"
    builder_cab_available: bool = True


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/live")


@app.post("/reset")
def reset(request: ResetRequest | None = None) -> dict[str, object]:
    observation = env.reset(task_id=request.task_id if request else None)
    return {"observation": observation.model_dump(), "done": False}


@app.post("/step")
def step(action: Action) -> dict[str, object]:
    try:
        result = env.step(action)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


@app.get("/state")
def state() -> dict[str, object]:
    try:
        return env.state()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/calls/latest")
def latest_call() -> dict[str, object]:
    try:
        current_state = env.state()
    except RuntimeError:
        if latest_call_cache:
            return latest_call_cache
        return {
            "available": False,
            "detail": "No active or cached call transcript is available yet.",
            "call_transcript": [],
        }

    opportunity = current_state["active_opportunity"]
    if opportunity.get("call_transcript"):
        return {
            "available": True,
            "opportunity_id": opportunity["opportunity_id"],
            "customer_name": opportunity["customer_name"],
            "customer_contacted": opportunity.get("customer_contacted", False),
            "call_outcome": opportunity.get("call_outcome"),
            "last_contact_note": opportunity.get("last_contact_note"),
            "call_transcript": opportunity.get("call_transcript", []),
        }
    if latest_call_cache:
        return latest_call_cache
    return {
        "available": False,
        "detail": "No active or cached call transcript is available yet.",
        "call_transcript": [],
    }


@app.get("/cab/providers")
def cab_providers() -> dict[str, object]:
    return {"providers": list_cab_providers()}


@app.post("/cab/bookings/preview")
def cab_booking_preview(request: CabBookingRequest) -> dict[str, object]:
    try:
        return preview_cab_booking(
            provider=request.provider,
            pickup_location=request.pickup_location,
            drop_location=request.drop_location,
            rider_name=request.rider_name,
            mode=request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cab/bookings")
def create_cab_booking(request: CabBookingRequest) -> dict[str, object]:
    try:
        return book_cab(
            provider=request.provider,
            pickup_location=request.pickup_location,
            drop_location=request.drop_location,
            rider_name=request.rider_name,
            mode=request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cab/mock-flow")
def cab_mock_flow(request: CabEligibilityMockRequest) -> dict[str, object]:
    inventory = [
        {
            "property_id": "mock_res_prop_001",
            "segment": "residential",
            "title": f"{request.property_type} in {request.property_location}",
            "location": request.property_location,
            "price_type": "sale",
            "price": request.budget or 9500000,
            "details": {
                "property_type": request.property_type,
                "builder_cab_available": request.builder_cab_available,
            },
        }
    ]
    lead = InboundLead(
        lead_id="mock_cab_flow_001",
        customer_name=request.customer_name,
        inquiry=request.inquiry,
        segment="residential",
        profession=request.profession,
        total_experience_years=request.total_experience_years,
        employment_type=request.employment_type,
        preferred_cab_provider=request.provider,
        customer_location=request.customer_location,
        budget=request.budget,
        location=request.property_location,
        timeline_days=request.timeline_days,
        property_type=request.property_type,
    )
    result = process_live_lead(lead, inventory=inventory)
    active = result.final_state["active_opportunity"]
    customer_response = active.get("cab_customer_response") or active.get("last_contact_note")
    return {
        "lead_id": result.lead_id,
        "final_stage": result.final_stage,
        "cab_flow": {
            "customer_wants_cab": active.get("cab_requested"),
            "builder_cab_available": active.get("builder_provides_cab"),
            "builder_cab_approved": active.get("builder_cab_approved"),
            "pickup_eligible": active.get("pickup_eligible"),
            "drop_eligible": active.get("drop_eligible"),
            "eligibility_status": active.get("cab_eligibility_status"),
            "customer_response": customer_response,
            "cab_booking_status": active.get("cab_booking_status"),
            "cab_booking_reference": active.get("cab_booking_reference"),
            "cab_booking_sla_seconds": active.get("cab_booking_sla_seconds"),
            "cab_booked_within_sla": active.get("cab_booked_within_sla"),
            "notifications": active.get("cab_notifications", []),
        },
        "action_trace": [step.action.model_dump(exclude_none=True) for step in result.action_trace],
    }


@app.get("/tasks")
def tasks() -> dict[str, object]:
    entries = []
    for task_id in env.available_tasks():
        task = load_task(task_id)
        entries.append(
            {
                "task_id": task["task_id"],
                "difficulty": task["difficulty"],
                "segment": task["opportunity"]["segment"],
            }
        )
    return {"tasks": entries}


@app.get("/metrics/conversions")
def get_conversion_metrics() -> dict[str, object]:
    return {
        "residential": conversion_metrics["residential"],
        "commercial": conversion_metrics["commercial"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/metrics/reset")
def reset_conversion_metrics() -> dict[str, str]:
    conversion_metrics["residential"] = {
        "total_leads": 0,
        "contacted": 0,
        "interested_in_visit": 0,
        "appointment_scheduled": 0,
        "deal_closed": 0,
    }
    conversion_metrics["commercial"] = {
        "total_leads": 0,
        "contacted": 0,
        "proposal_sent": 0,
        "negotiation": 0,
        "deal_closed": 0,
    }
    return {"status": "Conversion metrics reset"}


@app.get("/lead-categorization")
def get_lead_categorization() -> dict[str, object]:
    """Get current lead categorization and statistics"""
    return {
        "eligible_for_contact": lead_categorization["eligible_for_contact"],
        "scheduled_for_visit": lead_categorization["scheduled_for_visit"],
        "cold_leads": lead_categorization["cold_leads"],
        "qualification_pending": lead_categorization["qualification_pending"],
        "deal_closed": lead_categorization["deal_closed"],
        "summary": {
            "total_leads": sum(len(v) for v in lead_categorization.values()),
            "eligible_count": len(lead_categorization["eligible_for_contact"]),
            "scheduled_count": len(lead_categorization["scheduled_for_visit"]),
            "cold_count": len(lead_categorization["cold_leads"]),
            "pending_count": len(lead_categorization["qualification_pending"]),
            "closed_count": len(lead_categorization["deal_closed"]),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/lead-categorization/reset")
def reset_lead_categorization() -> dict[str, str]:
    """Reset lead categorization"""
    lead_categorization["eligible_for_contact"].clear()
    lead_categorization["scheduled_for_visit"].clear()
    lead_categorization["cold_leads"].clear()
    lead_categorization["qualification_pending"].clear()
    lead_categorization["deal_closed"].clear()
    return {"status": "Lead categorization reset"}


@app.get("/market-rates")
def get_market_rates(location: str | None = None, property_type: str | None = None) -> dict[str, object]:
    """Get market rates by location and property type"""
    result = {}
    
    for loc, property_types in market_rates.items():
        if location and loc.lower() != location.lower():
            continue
        
        result[loc] = {}
        for ptype, prices in property_types.items():
            if property_type and ptype.lower() != property_type.lower():
                continue
            
            if prices:
                avg_price = sum(p["price"] for p in prices) / len(prices)
                min_price = min(p["price"] for p in prices)
                max_price = max(p["price"] for p in prices)
                
                result[loc][ptype] = {
                    "average": avg_price,
                    "min": min_price,
                    "max": max_price,
                    "count": len(prices),
                    "latest": prices[-1]["price"] if prices else 0,
                }
    
    return {"market_rates": result, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/market-rates/track")
def track_market_rate(location: str, property_type: str, price: float) -> dict[str, str]:
    """Track a new property price for market rate analytics"""
    if location not in market_rates:
        market_rates[location] = {}
    
    if property_type not in market_rates[location]:
        market_rates[location][property_type] = []
    
    market_rates[location][property_type].append({
        "price": price,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    return {"status": "Market rate tracked", "location": location, "property_type": property_type, "price": price}


@app.get("/simulate/live-example", response_model=LiveTrafficSimulationResponse)
def simulate_live_example() -> LiveTrafficSimulationResponse:
    return simulate_live_traffic(DEFAULT_LIVE_LEADS)


@app.post("/simulate/live", response_model=LiveTrafficSimulationResponse)
def simulate_live(request: LiveTrafficSimulationRequest | None = None) -> LiveTrafficSimulationResponse:
    leads = request.leads if request and request.leads else DEFAULT_LIVE_LEADS
    return simulate_live_traffic(leads)


@app.get("/simulate/live/stream")
def simulate_live_stream(delay_seconds: float = 0.35) -> StreamingResponse:
    stream = _cache_call_stream(stream_live_traffic_events(DEFAULT_STREAM_LEADS, delay_seconds=max(delay_seconds, 0.0)))
    return StreamingResponse(stream, media_type="application/x-ndjson")


@app.post("/simulate/live/stream")
def simulate_live_stream_custom(
    request: LiveTrafficSimulationRequest | None = None,
    delay_seconds: float = 0.35,
) -> StreamingResponse:
    leads = request.leads if request and request.leads else DEFAULT_STREAM_LEADS
    stream = _cache_call_stream(stream_live_traffic_events(leads, delay_seconds=max(delay_seconds, 0.0)))
    return StreamingResponse(stream, media_type="application/x-ndjson")


def _cache_call_stream(stream):
    tracked_leads = set()
    for raw_event in stream:
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            yield raw_event
            continue

        payload = event.get("payload", {})
        lead_segment = payload.get("segment", "residential")
        lead_id = event.get("lead_id")
        
        # Track conversion metrics
        if event.get("event") == "lead_received":
            conversion_metrics[lead_segment]["total_leads"] += 1
            tracked_leads.add(lead_id)
        
        if event.get("event") == "lead_step":
            # Track customer contact
            if payload.get("customer_contacted") and lead_id not in tracked_leads:
                conversion_metrics[lead_segment]["contacted"] += 1
                tracked_leads.add(lead_id)
            
            # Track property recommendations for market rates
            if payload.get("recommended_property_id") and f"{lead_id}_property" not in tracked_leads:
                # Extract location and property_type from payload
                location = payload.get("location")
                property_type = payload.get("property_type") or payload.get("business_type")
                property_price = payload.get("property_price")
                
                if location and property_type and property_price:
                    if location not in market_rates:
                        market_rates[location] = {}
                    if property_type not in market_rates[location]:
                        market_rates[location][property_type] = []
                    
                    market_rates[location][property_type].append({
                        "price": property_price,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    tracked_leads.add(f"{lead_id}_property")
            
            # Track residential stages
            if lead_segment == "residential":
                if payload.get("interested_in_visit") and f"{lead_id}_visit" not in tracked_leads:
                    conversion_metrics[lead_segment]["interested_in_visit"] += 1
                    tracked_leads.add(f"{lead_id}_visit")
                if payload.get("appointment_type") and f"{lead_id}_appt" not in tracked_leads:
                    conversion_metrics[lead_segment]["appointment_scheduled"] += 1
                    tracked_leads.add(f"{lead_id}_appt")
            
            # Track commercial stages
            if lead_segment == "commercial":
                if payload.get("proposal_sent") and f"{lead_id}_prop" not in tracked_leads:
                    conversion_metrics[lead_segment]["proposal_sent"] += 1
                    tracked_leads.add(f"{lead_id}_prop")
                if payload.get("stage") == "negotiation" and f"{lead_id}_neg" not in tracked_leads:
                    conversion_metrics[lead_segment]["negotiation"] += 1
                    tracked_leads.add(f"{lead_id}_neg")
            
            if payload.get("call_transcript"):
                latest_call_cache.clear()
                latest_call_cache.update(
                    {
                        "opportunity_id": event.get("lead_id"),
                        "customer_name": payload.get("customer_name") or event.get("lead_id"),
                        "available": True,
                        "customer_contacted": True,
                        "call_outcome": payload.get("call_outcome"),
                        "last_contact_note": _last_customer_turn(payload.get("call_transcript", [])),
                        "call_transcript": payload.get("call_transcript", []),
                    }
                )
        
        if event.get("event") == "lead_completed":
            if payload.get("deal_closed") and f"{lead_id}_closed" not in tracked_leads:
                conversion_metrics[lead_segment]["deal_closed"] += 1
                tracked_leads.add(f"{lead_id}_closed")
                # Remove from other categories
                for category in lead_categorization:
                    lead_categorization[category] = [l for l in lead_categorization[category] if l.get("lead_id") != lead_id]
                # Categorize as dealt/closed
                lead_obj = {
                    "lead_id": lead_id,
                    "customer_name": payload.get("customer_name") or lead_id,
                    "property_type": payload.get("property_type") or payload.get("business_type") or "Unknown",
                }
                lead_categorization["deal_closed"].append(lead_obj)
            else:
                # Categorize leads at completion
                customer_name = payload.get("customer_name") or lead_id
                final_stage = payload.get("final_stage", "")
                missing_fields = payload.get("missing_fields")
                property_type = payload.get("property_type") or payload.get("business_type") or "Unknown"
                
                lead_obj = {
                    "lead_id": lead_id,
                    "customer_name": customer_name,
                    "property_type": property_type,
                }
                
                # Remove from any previous category
                for category in lead_categorization:
                    lead_categorization[category] = [l for l in lead_categorization[category] if l.get("lead_id") != lead_id]
                
                # Assign to appropriate category
                if missing_fields and len(missing_fields) > 0:
                    lead_categorization["qualification_pending"].append(lead_obj)
                elif final_stage in ["builder_appointment_scheduled", "landlord_meeting_scheduled"]:
                    lead_categorization["scheduled_for_visit"].append(lead_obj)
                elif final_stage in ["new", "receiving", "classified", "prioritized", "property_recommended"]:
                    lead_categorization["eligible_for_contact"].append(lead_obj)
                elif final_stage in ["move_to_nurture"]:
                    lead_categorization["cold_leads"].append(lead_obj)
                else:
                    lead_categorization["qualification_pending"].append(lead_obj)
        
        yield raw_event


def _last_customer_turn(call_transcript: list[dict[str, object]]) -> str | None:
    for turn in reversed(call_transcript):
        if turn.get("speaker") == "customer":
            text = turn.get("text")
            return text if isinstance(text, str) else None
    return None


@app.get("/dashboard/live", response_class=HTMLResponse)
def live_dashboard() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Live CRM Traffic Dashboard</title>
  <style>
    :root {
      --bg: linear-gradient(135deg, #f7f4ea 0%, #dce8f2 48%, #f4dbc9 100%);
      --panel: rgba(255, 255, 255, 0.78);
      --ink: #1f2c2d;
      --muted: #5e6a6b;
      --accent: #0d7c66;
      --accent-soft: #d8efe8;
      --warn: #b76e2b;
      --border: rgba(31, 44, 45, 0.12);
      --shadow: 0 18px 50px rgba(31, 44, 45, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background: var(--bg);
      min-height: 100vh;
    }
    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }
    .hero {
      display: grid;
      gap: 14px;
      margin-bottom: 24px;
    }
    .eyebrow {
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted);
    }
    h1 {
      margin: 0;
      font-size: clamp(2rem, 5vw, 4rem);
      line-height: 0.95;
      max-width: 10ch;
    }
    .sub {
      max-width: 62ch;
      font-size: 1.05rem;
      color: var(--muted);
    }
    .controls, .grid > section {
      border: 1px solid var(--border);
      background: var(--panel);
      backdrop-filter: blur(16px);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 14px;
      padding: 18px;
      margin-bottom: 18px;
    }
    button {
      border: none;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      padding: 12px 18px;
      font: inherit;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .status {
      color: var(--muted);
      font-size: 0.95rem;
    }
    .grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
    }
    section {
      padding: 18px;
      min-height: 420px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 1.15rem;
    }
    .lead-card, .event-row {
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.72);
    }
    .cab-panel {
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      background: rgba(247, 250, 244, 0.9);
      margin-bottom: 18px;
    }
    .cab-status-list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .cab-status-item {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 12px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.82);
      border: 1px solid var(--border);
      font-size: 0.95rem;
    }
    .cab-status-item .label {
      color: var(--muted);
    }
    .cab-status-item .value {
      font-weight: 700;
      color: var(--ink);
      text-align: right;
    }
    .cab-status-item.active .value {
      color: var(--accent);
    }
    .cab-status-item.good .value {
      color: #1c7c54;
    }
    .cab-status-item.bad .value {
      color: #a44a3f;
    }
    .cab-message {
      margin-top: 12px;
      padding: 12px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.82);
      border: 1px solid var(--border);
      color: var(--ink);
      min-height: 24px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 18px;
    }
    .form-grid .full {
      grid-column: 1 / -1;
    }
    label {
      display: grid;
      gap: 6px;
      font-size: 0.9rem;
      color: var(--muted);
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 10px 12px;
      background: rgba(255, 255, 255, 0.85);
      font: inherit;
      color: var(--ink);
    }
    textarea {
      min-height: 96px;
      resize: vertical;
    }
    .form-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }
    .secondary {
      background: #d9e7e4;
      color: #24453f;
    }
    .voice {
      background: #355c7d;
    }
    .voice-panel {
      border: 1px dashed var(--border);
      border-radius: 18px;
      padding: 14px;
      margin-bottom: 18px;
      background: rgba(242, 248, 250, 0.85);
    }
    .voice-log {
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.92rem;
      min-height: 22px;
    }
    .segment-group.hidden {
      display: none;
    }
    .lead-list, .event-list {
      display: grid;
      gap: 12px;
      max-height: 70vh;
      overflow: auto;
      padding-right: 4px;
    }
    .lead-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .score {
      display: inline-block;
      margin-top: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.9rem;
    }
    .event-tag {
      display: inline-block;
      margin-bottom: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #efe4d3;
      color: var(--warn);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.84rem;
      color: #263536;
    }
    .conversion-chart-container {
      position: relative;
      height: 350px;
      margin-bottom: 16px;
    }
    .conversion-chart-section {
      display: flex;
      flex-direction: column;
      min-height: 400px;
    }
    .funnel-metrics {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric-box {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.9);
      text-align: center;
      font-size: 0.9rem;
    }
    .metric-box .value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--accent);
      margin: 4px 0;
    }
    .metric-box .label {
      font-size: 0.85rem;
      color: var(--muted);
    }
    .reset-metrics-btn {
      padding: 8px 12px;
      font-size: 0.85rem;
      margin-top: auto;
    }
    .market-rate-chart-container {
      position: relative;
      height: 360px;
      margin-bottom: 16px;
    }
    .market-rate-filter {
      display: flex;
      gap: 10px;
      margin-bottom: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .market-rate-filter select {
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: white;
      font-size: 0.9rem;
    }
    .market-info-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .market-info-cell {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px;
      background: rgba(255, 255, 255, 0.9);
      font-size: 0.85rem;
      text-align: center;
    }
    .market-info-cell .loc {
      font-weight: 700;
      color: var(--accent);
      font-size: 0.9rem;
      margin-bottom: 6px;
    }
    .market-info-cell .ptype {
      color: var(--muted);
      font-size: 0.8rem;
      margin-bottom: 4px;
    }
    .market-info-cell .price {
      font-weight: 600;
      color: var(--ink);
    }
    .lead-categorization-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .lead-category-box {
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.9);
      text-align: center;
      font-size: 0.9rem;
    }
    .lead-category-box.eligible {
      border-left: 4px solid #0d7c66;
      background: rgba(13, 124, 102, 0.05);
    }
    .lead-category-box.scheduled {
      border-left: 4px solid #1f5aa0;
      background: rgba(31, 90, 160, 0.05);
    }
    .lead-category-box.cold {
      border-left: 4px solid #b76e2b;
      background: rgba(183, 110, 43, 0.05);
    }
    .lead-category-box.pending {
      border-left: 4px solid #8a7a1f;
      background: rgba(138, 122, 31, 0.05);
    }
    .lead-category-box.closed {
      border-left: 4px solid #1c7c54;
      background: rgba(28, 124, 84, 0.05);
    }
    .lead-category-box .count {
      font-size: 1.8rem;
      font-weight: 700;
      color: var(--ink);
      margin: 6px 0;
    }
    .lead-category-box .label {
      font-size: 0.8rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .lead-category-box .details {
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 8px;
      max-height: 60px;
      overflow-y: auto;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      h1 { max-width: none; }
      .form-grid { grid-template-columns: 1fr; }
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div class="eyebrow">Agentic CRM Demo</div>
      <h1>Live Lead Processing Dashboard</h1>
      <div class="sub">Streams multiple simulated inbound leads the way a brokerage inbox might receive them, then shows how the autonomous agent qualifies, prioritizes, matches inventory, and moves each deal forward.</div>
    </div>
    <div class="controls">
      <button id="startButton">Start Stream</button>
      <div class="status" id="statusText">Ready to simulate inbound CRM traffic.</div>
    </div>
    <div class="controls, .grid > section">
      <div style="flex: 1;">
        <div style="font-size: 0.95rem; color: var(--muted); margin-bottom: 8px;">Business Metrics</div>
        <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
          <select id="segmentFilter" style="padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: white;">
            <option value="all">All Segments</option>
            <option value="residential">Residential Only</option>
            <option value="commercial">Commercial Only</option>
          </select>
          <button id="resetMetricsBtn" class="secondary" style="padding: 8px 12px; font-size: 0.9rem;">Reset Metrics</button>
        </div>
      </div>
    </div>
    <div style="border: 1px solid var(--border); background: var(--panel); backdrop-filter: blur(16px); border-radius: 24px; box-shadow: var(--shadow); padding: 18px; margin-bottom: 18px;">
      <h2 style="margin-top: 0;">Lead Conversion Funnel</h2>
      <div class="conversion-chart-container">
        <canvas id="conversionChart"></canvas>
      </div>
      <div class="funnel-metrics" id="funnelMetrics"></div>
    </div>
    <div style="border: 1px solid var(--border); background: var(--panel); backdrop-filter: blur(16px); border-radius: 24px; box-shadow: var(--shadow); padding: 18px; margin-bottom: 18px;">
      <h2 style="margin-top: 0; margin-bottom: 16px;">Lead Categorization & Qualification Status</h2>
      <div class="lead-categorization-grid" id="leadCategorizationGrid">
        <div class="lead-category-box eligible" style="border-left: 4px solid #4CAF50;">
          <div class="category-label">Eligible for Contact</div>
          <div class="category-count" id="count-eligible-for-contact">0</div>
          <div class="category-details" id="details-eligible-for-contact"></div>
        </div>
        <div class="lead-category-box scheduled" style="border-left: 4px solid #2196F3;">
          <div class="category-label">Scheduled for Visit</div>
          <div class="category-count" id="count-scheduled-for-visit">0</div>
          <div class="category-details" id="details-scheduled-for-visit"></div>
        </div>
        <div class="lead-category-box cold" style="border-left: 4px solid #795548;">
          <div class="category-label">Cold Leads</div>
          <div class="category-count" id="count-cold-leads">0</div>
          <div class="category-details" id="details-cold-leads"></div>
        </div>
        <div class="lead-category-box pending" style="border-left: 4px solid #FFC107;">
          <div class="category-label">Qualification Pending</div>
          <div class="category-count" id="count-qualification-pending">0</div>
          <div class="category-details" id="details-qualification-pending"></div>
        </div>
        <div class="lead-category-box closed" style="border-left: 4px solid #1B5E20;">
          <div class="category-label">Deal Closed</div>
          <div class="category-count" id="count-deal-closed">0</div>
          <div class="category-details" id="details-deal-closed"></div>
        </div>
      </div>
    </div>
    <div style="border: 1px solid var(--border); background: var(--panel); backdrop-filter: blur(16px); border-radius: 24px; box-shadow: var(--shadow); padding: 18px; margin-bottom: 18px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <h2 style="margin: 0;">Market Rate Analysis</h2>
        <span id="marketRateTitle" style="font-size: 0.95rem; color: var(--accent); font-weight: 600;">Analyzing: 2BHK apartment</span>
      </div>
      <div class="market-rate-filter">
        <select id="marketLocationFilter" style="padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: white;">
          <option value="all">All Locations</option>
          <option value="Whitefield">Whitefield</option>
          <option value="Sarjapur">Sarjapur</option>
          <option value="Marathahalli">Marathahalli</option>
          <option value="Indiranagar">Indiranagar</option>
          <option value="CBD Retail District">CBD Retail District</option>
        </select>
        <span style="font-size: 0.9rem; color: var(--muted);">Show pricing trends by location</span>
      </div>
      <div class="market-rate-chart-container">
        <canvas id="marketRateChart"></canvas>
      </div>
      <div class="market-info-grid" id="marketInfoGrid"></div>
    </div>
    <div class="grid">
      <section>
        <h2>Manual Lead Entry & Voice Intake</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
          <div class="voice-panel">
            <div><strong>Voice Assistant</strong></div>
            <div class="sub">Use your microphone to capture a lead verbally. Best supported in Chromium-based browsers.</div>
            <div class="form-actions" style="margin-top: 12px; margin-bottom: 0;">
              <button id="startVoiceIntakeButton" class="voice">Start Voice Intake</button>
              <button id="dictateInquiryButton" class="voice">Dictate Inquiry</button>
              <button id="playLatestCallButton" class="secondary">Play Latest Call</button>
            </div>
            <div class="voice-log" id="voiceLog">Voice assistant idle.</div>
          </div>
          <div style="border: 1px solid var(--border); border-radius: 12px; padding: 16px; background: var(--panel);">
            <div style="margin-bottom: 8px;"><strong>Test Input Editor</strong> (Fallback when voice fails)</div>
            <div class="sub" style="margin-bottom: 12px; font-size: 0.85rem;">Paste or type inquiry text directly (for testing when voice recognition unavailable)</div>
            <textarea id="testInquiryInput" placeholder="E.g., Looking for a 3BHK apartment in Whitefield. Budget is 1 crore and need to move in 60 days." style="width: 100%; height: 120px; padding: 8px; border: 1px solid var(--border); border-radius: 8px; font-family: monospace; font-size: 0.9rem; resize: vertical;"></textarea>
            <button id="submitTestInquiryButton" style="margin-top: 8px; padding: 8px 16px; background: #2196F3; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem;">Use Test Input</button>
            <div id="testInputLog" style="margin-top: 8px; font-size: 0.8rem; color: var(--muted); line-height: 1.4;"></div>
          </div>
        </div>
        <div class="form-grid">
          <label>
            Lead ID
            <input id="leadId" value="manual_res_001" />
          </label>
          <label>
            Customer Name
            <input id="customerName" value="Demo Buyer" />
          </label>
          <label>
            Profession
            <input id="profession" value="software engineer" />
          </label>
          <label>
            Employment Type
            <select id="employmentType">
              <option value="salaried" selected>salaried</option>
              <option value="business">business</option>
              <option value="self-employed">self-employed</option>
            </select>
          </label>
          <label>
            Segment
            <select id="segment">
              <option value="residential" selected>residential</option>
              <option value="commercial">commercial</option>
            </select>
          </label>
          <label>
            Location
            <input id="location" value="Whitefield" />
          </label>
          <label>
            Customer Current Location
            <input id="customerLocation" value="Marathahalli" />
          </label>
          <label>
            Budget
            <input id="budget" type="number" value="9500000" />
          </label>
          <label>
            Timeline Days
            <input id="timelineDays" type="number" value="30" />
          </label>
          <label>
            Total Experience (Years)
            <input id="totalExperienceYears" type="number" value="7" />
          </label>
          <label class="segment-group residential-group">
            Property Type
            <input id="propertyType" value="2BHK apartment" />
          </label>
          <label class="segment-group commercial-group hidden">
            Business Type
            <input id="businessType" value="" placeholder="Use for commercial leads" />
          </label>
          <label class="segment-group commercial-group hidden">
            Square Feet Min
            <input id="squareFeetMin" type="number" value="" />
          </label>
          <label class="segment-group commercial-group hidden">
            Square Feet Max
            <input id="squareFeetMax" type="number" value="" />
          </label>
          <label class="full">
            Inquiry
            <textarea id="inquiry">Looking for a 2BHK apartment in Whitefield. Budget is 95 lakhs and I want to move in within 30 days. Please suggest options.</textarea>
          </label>
          <label class="full">
            Missing Fields
            <input id="missingFields" value="" placeholder="Comma-separated, for example: budget,timeline_days,financing_status" />
          </label>
        </div>
        <div class="form-actions">
          <button id="submitManualButton">Run Manual Lead</button>
          <button id="loadDefaultButton" class="secondary">Load Whitefield Example</button>
          <button id="loadCommercialButton" class="secondary">Load Commercial Example</button>
        </div>
        <h2>Cab Operations</h2>
        <div class="cab-panel">
          <div class="sub">Residential lead runs update this section with cab eligibility, booking progress, notifications, and SLA timing.</div>
          <div class="cab-status-list" id="cabStatusList">
            <div class="cab-status-item"><span class="label">Cab Eligibility</span><span class="value">Awaiting residential lead</span></div>
            <div class="cab-status-item"><span class="label">Builder Approval</span><span class="value">Not checked</span></div>
            <div class="cab-status-item"><span class="label">Pickup Eligibility</span><span class="value">Not checked</span></div>
            <div class="cab-status-item"><span class="label">Drop Eligibility</span><span class="value">Not checked</span></div>
            <div class="cab-status-item"><span class="label">Cab Booking</span><span class="value">Awaiting confirmation</span></div>
            <div class="cab-status-item"><span class="label">Booking Reference</span><span class="value">Pending</span></div>
            <div class="cab-status-item"><span class="label">Cab Timing SLA</span><span class="value">Pending</span></div>
            <div class="cab-status-item"><span class="label">Chat Notification</span><span class="value">Pending</span></div>
            <div class="cab-status-item"><span class="label">SMS Notification</span><span class="value">Pending</span></div>
            <div class="cab-status-item"><span class="label">WhatsApp Notification</span><span class="value">Pending</span></div>
          </div>
          <div class="cab-message" id="cabMessage">Run a residential lead to see the cab operations flow.</div>
        </div>
        <h2>Lead Outcomes</h2>
        <div class="lead-list" id="leadList"></div>
      </section>
      <section>
        <h2>Live Event Feed</h2>
        <div class="event-list" id="eventList"></div>
      </section>
    </div>
  </div>
  <script>
    const startButton = document.getElementById("startButton");
    const statusText = document.getElementById("statusText");
    const leadList = document.getElementById("leadList");
    const eventList = document.getElementById("eventList");
    const cabStatusList = document.getElementById("cabStatusList");
    const cabMessage = document.getElementById("cabMessage");
    const submitManualButton = document.getElementById("submitManualButton");
    const loadDefaultButton = document.getElementById("loadDefaultButton");
    const loadCommercialButton = document.getElementById("loadCommercialButton");
    const segmentSelect = document.getElementById("segment");
    const startVoiceIntakeButton = document.getElementById("startVoiceIntakeButton");
    const dictateInquiryButton = document.getElementById("dictateInquiryButton");
    const playLatestCallButton = document.getElementById("playLatestCallButton");
    const voiceLog = document.getElementById("voiceLog");
    const submitTestInquiryButton = document.getElementById("submitTestInquiryButton");
    const testInquiryInput = document.getElementById("testInquiryInput");
    const testInputLog = document.getElementById("testInputLog");
    const leads = new Map();
    const cabVoiceState = new Map();
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const recognitionSupported = Boolean(SpeechRecognition);
    const playbackSupported = Boolean(window.speechSynthesis);
    let recognitionBusy = false;
    
    // Conversion metrics and chart
    const segmentFilter = document.getElementById("segmentFilter");
    const resetMetricsBtn = document.getElementById("resetMetricsBtn");
    const funnelMetrics = document.getElementById("funnelMetrics");
    let conversionChart = null;
    
    // Market rates chart
    const marketLocationFilter = document.getElementById("marketLocationFilter");
    const marketInfoGrid = document.getElementById("marketInfoGrid");
    const propertyTypeInput = document.getElementById("propertyType");
    const businessTypeInput = document.getElementById("businessType");
    let marketRateChart = null;

    function renderLeadCard(leadId) {
      const lead = leads.get(leadId);
      if (!lead) return;
      let card = document.getElementById(`lead-${leadId}`);
      if (!card) {
        card = document.createElement("div");
        card.className = "lead-card";
        card.id = `lead-${leadId}`;
        leadList.prepend(card);
      }
      card.innerHTML = `
        <div class="lead-meta">
          <strong>${lead.customer_name || leadId}</strong>
          <span>${leadId}</span>
        </div>
        <div>${lead.inquiry || ""}</div>
        ${lead.last_contact_note ? "<div class='score'>Call Note: " + lead.last_contact_note + "</div>" : ""}
        <div class="score">Stage: ${lead.final_stage || lead.stage || "receiving"} | Score: ${lead.final_score ?? lead.grader_score ?? 0}</div>
      `;
    }

    function addEventRow(event) {
      const row = document.createElement("div");
      row.className = "event-row";
      
      // Map deal stages from event types
      const stageEmojis = {
        'send_proposal': '📧',
        'customer_follow_up': '☎️',
        'send_negotiation_offer': '🤝',
        'send_payment_reminder': '💳',
        'process_booking_payment': '💰',
        'finalize_deal': '🎉',
        'lead_received': '📌',
        'lead_step': '🔄'
      };
      
      const stageNames = {
        'send_proposal': 'Proposal',
        'customer_follow_up': 'Follow-up',
        'send_negotiation_offer': 'Negotiation',
        'send_payment_reminder': 'Payment Reminder',
        'process_booking_payment': 'Payment Received',
        'finalize_deal': 'Deal Closed',
        'lead_received': 'Lead Captured',
        'lead_step': 'Pipeline Step'
      };
      
      const emoji = stageEmojis[event.event] || '📝';
      const stageName = stageNames[event.event] || event.event;
      const timestamp = new Date().toLocaleTimeString();
      const leadId = event.lead_id || event.payload?.lead_id || 'Unknown';
      const customerName = event.payload?.customer_name || 'N/A';
      
      // Extract key details based on event type
      let details = '';
      if (event.payload) {
        if (event.payload.booking_amount) {
          details += `Amount: ₹${(event.payload.booking_amount / 100000).toFixed(1)}L`;
        } else if (event.payload.inquiry) {
          details += `Inquiry: ${event.payload.inquiry.substring(0, 60)}...`;
        }
        if (event.payload.action_type) {
          details += ` | Action: ${event.payload.action_type}`;
        }
        if (event.payload.negotiation_round !== undefined) {
          details += ` | Round: ${event.payload.negotiation_round}`;
        }
        if (event.payload.follow_up_count !== undefined) {
          details += ` | Attempt: ${event.payload.follow_up_count}`;
        }
      }
      
      // Create formatted event card (collapsible)
      row.innerHTML = `
        <div style="display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <span style="font-size: 1.2em;">${emoji}</span>
              <strong style="color: #fff;">${stageName}</strong>
              <span style="font-size: 0.8em; color: rgba(255,255,255,0.6);">${timestamp}</span>
            </div>
            <div style="font-size: 0.85em; color: rgba(255,255,255,0.8); margin-left: 28px;">
              <strong>Lead:</strong> ${customerName} (${leadId})
              ${details ? "<br><strong>Details:</strong> " + details : ""}
            </div>
          </div>
          <button style="padding: 4px 8px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; color: #fff; cursor: pointer; font-size: 0.8em;" onclick="this.parentElement.parentElement.classList.toggle('expanded');">Details</button>
        </div>
        <details style="margin-top: 8px; margin-left: 28px; font-size: 0.85em; color: rgba(255,255,255,0.7);">
          <summary style="cursor: pointer; color: rgba(255,255,255,0.6);">Raw Event Data</summary>
          <pre style="background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 8px;">${JSON.stringify(event, null, 2)}</pre>
        </details>
      `;
      
      eventList.prepend(row);
    }

    function resetCabPanel() {
      cabStatusList.innerHTML = `
        <div class="cab-status-item"><span class="label">Cab Eligibility</span><span class="value">Awaiting residential lead</span></div>
        <div class="cab-status-item"><span class="label">Builder Approval</span><span class="value">Not checked</span></div>
        <div class="cab-status-item"><span class="label">Pickup Eligibility</span><span class="value">Not checked</span></div>
        <div class="cab-status-item"><span class="label">Drop Eligibility</span><span class="value">Not checked</span></div>
        <div class="cab-status-item"><span class="label">Cab Booking</span><span class="value">Awaiting confirmation</span></div>
        <div class="cab-status-item"><span class="label">Booking Reference</span><span class="value">Pending</span></div>
        <div class="cab-status-item"><span class="label">Cab Timing SLA</span><span class="value">Pending</span></div>
        <div class="cab-status-item"><span class="label">Chat Notification</span><span class="value">Pending</span></div>
        <div class="cab-status-item"><span class="label">SMS Notification</span><span class="value">Pending</span></div>
        <div class="cab-status-item"><span class="label">WhatsApp Notification</span><span class="value">Pending</span></div>
      `;
      cabMessage.textContent = "Run a residential lead to see the cab operations flow.";
    }

    function setCabStatus(label, value, tone = "") {
      const rows = Array.from(cabStatusList.querySelectorAll(".cab-status-item"));
      const row = rows.find((item) => item.querySelector(".label")?.textContent === label);
      if (!row) return;
      row.classList.remove("active", "good", "bad");
      if (tone) {
        row.classList.add(tone);
      }
      const valueNode = row.querySelector(".value");
      if (valueNode) {
        valueNode.textContent = value;
      }
    }

    function updateCabPanelFromPayload(payload, lead = {}) {
      if (!payload) return;
      if (lead.segment === "commercial") {
        cabMessage.textContent = "Cab operations are only shown for residential leads in this dashboard.";
        return;
      }
      const voiceState = cabVoiceState.get(lead.customer_name || "default") || {
        initiationAnnounced: false,
        bookedAnnounced: false,
        notificationsAnnounced: false,
      };

      if (payload.action?.action_type === "confirm_site_visit_interest") {
        setCabStatus("Cab Eligibility", "Awaiting builder approval", "active");
        setCabStatus("Cab Booking", "Awaiting cab booking", "active");
        cabMessage.textContent = "Customer has confirmed site-visit interest and asked for cab support.";
      }

      if (payload.builder_cab_approved !== undefined || payload.pickup_eligible !== undefined || payload.drop_eligible !== undefined) {
        const eligible = Boolean(payload.builder_cab_approved && payload.pickup_eligible && payload.drop_eligible);
        setCabStatus("Builder Approval", payload.builder_cab_approved ? "Approved" : "Not approved", payload.builder_cab_approved ? "good" : "bad");
        setCabStatus("Pickup Eligibility", payload.pickup_eligible ? "Eligible" : "Not eligible", payload.pickup_eligible ? "good" : "bad");
        setCabStatus("Drop Eligibility", payload.drop_eligible ? "Eligible" : "Not eligible", payload.drop_eligible ? "good" : "bad");
        setCabStatus("Cab Eligibility", eligible ? "Cab eligible" : "Cab not eligible", eligible ? "good" : "bad");
      }

      if (payload.cab_customer_response) {
        cabMessage.textContent = payload.cab_customer_response;
      }

      if (
        payload.action?.action_type === "respond_cab_eligibility"
        && payload.builder_cab_approved
        && !voiceState.initiationAnnounced
      ) {
        voiceState.initiationAnnounced = true;
        const providerHint = document.getElementById("employmentType").value === "salaried" ? "Uber" : "Ola";
        const announcement = `${payload.cab_customer_response} We are now initiating your cab booking with ${providerHint}. Please wait up to 59 seconds while I fetch the booking details.`;
        voiceLog.textContent = announcement;
        playBeep(700, 140);
        speak(announcement);
      }

      if (payload.action?.action_type === "book_cab") {
        setCabStatus("Cab Booking", payload.cab_booking_reference ? "Cab booked" : "Awaiting cab booking", payload.cab_booking_reference ? "good" : "active");
      }

      if (payload.cab_booking_reference) {
        setCabStatus("Booking Reference", payload.cab_booking_reference, "good");
        setCabStatus("Cab Timing SLA", "Booked within 59 seconds", "good");
        if (!voiceState.bookedAnnounced) {
          voiceState.bookedAnnounced = true;
          const providerName = payload.action?.cab_provider
            || lead.preferred_cab_provider
            || (document.getElementById("employmentType").value === "salaried" ? "Uber" : "Ola");
          const bookedMessage = `Your cab has been booked with ${providerName}. Your booking reference is ${payload.cab_booking_reference}.`;
          voiceLog.textContent = bookedMessage;
          playBeep(760, 140);
          speak(bookedMessage);
        }
      }

      const notifications = payload.cab_notifications || [];
      const byChannel = new Map(notifications.map((item) => [item.channel, item]));
      if (byChannel.has("chat")) {
        setCabStatus("Chat Notification", "Notification sent", "good");
      }
      if (byChannel.has("sms")) {
        setCabStatus("SMS Notification", "Notification sent", "good");
      }
      if (byChannel.has("whatsapp")) {
        setCabStatus("WhatsApp Notification", "Notification sent", "good");
      }
      if (notifications.length && !voiceState.notificationsAnnounced) {
        voiceState.notificationsAnnounced = true;
        const notificationMessage = "The cab details have also been shared on chat, SMS, and WhatsApp.";
        voiceLog.textContent = notificationMessage;
        playBeep(820, 120);
        speak(notificationMessage);
      }
      cabVoiceState.set(lead.customer_name || "default", voiceState);
    }

    function resetBoards() {
      leadList.innerHTML = "";
      eventList.innerHTML = "";
      leads.clear();
      cabVoiceState.clear();
      resetCabPanel();
    }

    function manualPayload() {
      const numberOrNull = (value) => value === "" ? null : Number(value);
      const rawMissing = document.getElementById("missingFields").value.trim();
      return {
        leads: [
          {
            lead_id: document.getElementById("leadId").value.trim() || "manual_lead_001",
            customer_name: document.getElementById("customerName").value.trim() || "Demo Lead",
            inquiry: document.getElementById("inquiry").value.trim(),
            segment: document.getElementById("segment").value,
            profession: document.getElementById("profession").value.trim() || null,
            total_experience_years: numberOrNull(document.getElementById("totalExperienceYears").value.trim()),
            employment_type: document.getElementById("employmentType").value || null,
            customer_location: document.getElementById("customerLocation").value.trim() || null,
            budget: numberOrNull(document.getElementById("budget").value.trim()),
            location: document.getElementById("location").value.trim() || null,
            timeline_days: numberOrNull(document.getElementById("timelineDays").value.trim()),
            property_type: document.getElementById("propertyType").value.trim() || null,
            business_type: document.getElementById("businessType").value.trim() || null,
            square_feet_min: numberOrNull(document.getElementById("squareFeetMin").value.trim()),
            square_feet_max: numberOrNull(document.getElementById("squareFeetMax").value.trim()),
            missing_fields: rawMissing ? rawMissing.split(",").map(item => item.trim()).filter(Boolean) : []
          }
        ]
      };
    }

    function loadWhitefieldExample() {
      document.getElementById("leadId").value = "manual_res_001";
      document.getElementById("customerName").value = "Aarav Mehta";
      document.getElementById("profession").value = "software engineer";
      document.getElementById("employmentType").value = "salaried";
      document.getElementById("segment").value = "residential";
      document.getElementById("location").value = "Whitefield";
      document.getElementById("customerLocation").value = "Marathahalli";
      document.getElementById("budget").value = "9500000";
      document.getElementById("timelineDays").value = "30";
      document.getElementById("totalExperienceYears").value = "7";
      document.getElementById("propertyType").value = "2BHK apartment";
      document.getElementById("businessType").value = "";
      document.getElementById("squareFeetMin").value = "";
      document.getElementById("squareFeetMax").value = "";
      document.getElementById("inquiry").value = "Looking for a 2BHK apartment in Whitefield. Budget is 95 lakhs and I want to move in within 30 days. Please suggest options.";
      document.getElementById("missingFields").value = "";
      syncSegmentFields();
    }

    function loadCommercialExample() {
      document.getElementById("leadId").value = "manual_com_001";
      document.getElementById("customerName").value = "Bean Street Cafe";
      document.getElementById("profession").value = "founder";
      document.getElementById("employmentType").value = "business";
      document.getElementById("segment").value = "commercial";
      document.getElementById("location").value = "CBD Retail District";
      document.getElementById("customerLocation").value = "Indiranagar";
      document.getElementById("budget").value = "320000";
      document.getElementById("timelineDays").value = "45";
      document.getElementById("totalExperienceYears").value = "11";
      document.getElementById("propertyType").value = "";
      document.getElementById("businessType").value = "cafe";
      document.getElementById("squareFeetMin").value = "2500";
      document.getElementById("squareFeetMax").value = "3000";
      document.getElementById("inquiry").value = "We need 2500 to 3000 square feet in a high-footfall retail street. Our opening target is in 45 days. We can stretch to 3.2 lakh monthly if the fit and frontage are strong.";
      document.getElementById("missingFields").value = "";
      syncSegmentFields();
    }

    function syncSegmentFields() {
      const segment = segmentSelect.value;
      document.querySelectorAll(".residential-group").forEach((node) => node.classList.toggle("hidden", segment !== "residential"));
      document.querySelectorAll(".commercial-group").forEach((node) => node.classList.toggle("hidden", segment !== "commercial"));
      document.getElementById("propertyType").disabled = segment !== "residential";
      document.getElementById("businessType").disabled = segment !== "commercial";
      document.getElementById("squareFeetMin").disabled = segment !== "commercial";
      document.getElementById("squareFeetMax").disabled = segment !== "commercial";
      loadDefaultButton.textContent = segment === "commercial" ? "Load Residential Example" : "Load Whitefield Example";
    }

    function preferredVoice() {
      if (!playbackSupported) {
        return null;
      }
      const voices = window.speechSynthesis.getVoices();
      return voices.find((voice) => {
        const name = String(voice.name || "").toLowerCase();
        return name.includes("google") || name.includes("microsoft") || String(voice.lang || "").toLowerCase().startsWith("en");
      }) || voices[0] || null;
    }

    function speak(text, callbacks = {}) {
      if (!playbackSupported || !text) {
        if (callbacks.onend) callbacks.onend();
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = preferredVoice();
      utterance.rate = 0.98;
      utterance.pitch = 1;
      utterance.volume = 1;
      utterance.onend = () => {
        if (callbacks.onend) callbacks.onend();
      };
      utterance.onerror = () => {
        if (callbacks.onerror) callbacks.onerror();
        if (callbacks.onend) callbacks.onend();
      };
      window.speechSynthesis.speak(utterance);
    }

    function stopSpeechPlayback() {
      if (playbackSupported) {
        window.speechSynthesis.cancel();
      }
    }

    function playBeep(frequency = 880, durationMs = 140) {
      if (!AudioContextClass) return;
      try {
        const context = new AudioContextClass();
        const oscillator = context.createOscillator();
        const gainNode = context.createGain();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        gainNode.gain.setValueAtTime(0.001, context.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.01);
        gainNode.gain.exponentialRampToValueAtTime(0.001, context.currentTime + durationMs / 1000);
        oscillator.connect(gainNode);
        gainNode.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + durationMs / 1000);
        oscillator.onended = () => {
          context.close().catch(() => {});
        };
      } catch (error) {
        // Ignore audio context errors when browser blocks autoplay.
      }
    }

    function heardSkipIntent(text) {
      const normalized = String(text || "").trim().toLowerCase();
      return normalized === "skip" || normalized === "not required" || normalized.includes("skip") || normalized.includes("not required");
    }

    function cleanSpokenText(text) {
      return String(text || "")
        .replace(/\bdouble\b/gi, "2")
        .replace(/\btriple\b/gi, "3")
        .replace(/\bfour bedroom\b/gi, "4 bhk")
        .replace(/\bthree bedroom\b/gi, "3 bhk")
        .replace(/\btwo bedroom\b/gi, "2 bhk")
        .replace(/\bone bedroom\b/gi, "1 bhk")
        .replace(/\s+/g, " ")
        .trim();
    }

    function parseEmploymentType(text) {
      const normalized = cleanSpokenText(text).toLowerCase();
      if (normalized.includes("business")) return "business";
      if (normalized.includes("self")) return "self-employed";
      return "salaried";
    }

    function parseSegment(text) {
      const normalized = cleanSpokenText(text).toLowerCase();
      return normalized.includes("commercial") ? "commercial" : "residential";
    }

    function parseBudgetValue(text) {
      const normalized = cleanSpokenText(text).toLowerCase();
      const digits = normalized.replace(/[^0-9]/g, "");
      if (!digits) return "";
      const numeric = Number(digits);
      if (normalized.includes("crore")) return String(numeric * 10000000);
      if (normalized.includes("lakh") || normalized.includes("lakhs")) return String(numeric * 100000);
      return String(numeric);
    }

    function parseDaysValue(text) {
      const digits = cleanSpokenText(text).replace(/[^0-9]/g, "");
      return digits || "";
    }

    function parseSquareFeetValue(text) {
      const digits = cleanSpokenText(text).replace(/[^0-9]/g, "");
      return digits || "";
    }

    function inferLocation(text) {
      const normalized = cleanSpokenText(text);
      const knownLocations = [
        "Whitefield",
        "Marathahalli",
        "Sarjapur",
        "Indiranagar",
        "Koramangala",
        "HSR Layout",
        "Banashankari",
        "MG Road",
        "CBD Retail District",
      ];
      const matched = knownLocations.find((item) => normalized.toLowerCase().includes(item.toLowerCase()));
      if (matched) return matched;
      return normalized.replace(/^(in|at|from|near)\s+/i, "").trim();
    }

    function inferResidentialPropertyType(text) {
      const normalized = cleanSpokenText(text).toLowerCase();
      if (normalized.includes("4 bhk")) return "4BHK apartment";
      if (normalized.includes("3 bhk")) return "3BHK apartment";
      if (normalized.includes("2 bhk")) return "2BHK apartment";
      if (normalized.includes("1 bhk")) return "1BHK apartment";
      if (normalized.includes("villa")) return "villa";
      if (normalized.includes("plot")) return "plot";
      return cleanSpokenText(text);
    }

    function inferBusinessType(text) {
      const normalized = cleanSpokenText(text).toLowerCase();
      if (normalized.includes("cafe")) return "cafe";
      if (normalized.includes("restaurant")) return "restaurant";
      if (normalized.includes("office")) return "office";
      if (normalized.includes("retail")) return "retail";
      return cleanSpokenText(text);
    }

    function applyVoiceIntelligence() {
      const inquiry = cleanSpokenText(document.getElementById("inquiry").value);
      const segment = document.getElementById("segment").value;
      const locationInput = document.getElementById("location");
      const pickupInput = document.getElementById("customerLocation");
      const budgetInput = document.getElementById("budget");
      const timelineInput = document.getElementById("timelineDays");

      if (inquiry) {
        if (!locationInput.value.trim()) {
          const inferredLocation = inferLocation(inquiry);
          if (inferredLocation) {
            locationInput.value = inferredLocation;
          }
        }
        if (!budgetInput.value.trim()) {
          const inferredBudget = parseBudgetValue(inquiry);
          if (inferredBudget) {
            budgetInput.value = inferredBudget;
          }
        }
        if (!timelineInput.value.trim()) {
          const inferredTimeline = parseDaysValue(inquiry);
          if (inferredTimeline) {
            timelineInput.value = inferredTimeline;
          }
        }
        if (segment === "residential") {
          const propertyTypeInput = document.getElementById("propertyType");
          if (!propertyTypeInput.value.trim()) {
            propertyTypeInput.value = inferResidentialPropertyType(inquiry);
          }
          if (!pickupInput.value.trim() && inquiry.toLowerCase().includes("pickup")) {
            pickupInput.value = inferLocation(inquiry);
          }
        } else {
          const businessTypeInput = document.getElementById("businessType");
          if (!businessTypeInput.value.trim()) {
            businessTypeInput.value = inferBusinessType(inquiry);
          }
        }
      }
    }

    function waitForSpeech(promptText, options = {}) {
      if (!recognitionSupported) {
        return Promise.reject(new Error("Speech recognition is not supported in this browser."));
      }

      const {
        retries = 1,
        spokenPrompt = true,
        timeoutMs = 4500,
        allowSkip = false,
        emptyValue = "",
      } = options;

      voiceLog.textContent = promptText;

      return new Promise((resolve, reject) => {
        const recognition = new SpeechRecognition();
        recognition.lang = "en-US";
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.continuous = true;

        let settled = false;
        let recognitionTimeout = null;
        let finalTranscript = "";

        recognition.onresult = (event) => {
          let interimTranscript = "";
          for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const transcript = event.results[i][0].transcript.trim();
            if (event.results[i].isFinal) {
              finalTranscript += ` ${transcript}`;
            } else {
              interimTranscript += ` ${transcript}`;
            }
          }
          const heard = (finalTranscript || interimTranscript).trim();
          if (heard) {
            voiceLog.textContent = `Heard: ${heard}`;
            if (allowSkip && heardSkipIntent(heard)) {
              settled = true;
              try {
                recognition.stop();
              } catch (error) {
                // ignore
              }
            }
          }
        };
        recognition.onerror = (event) => {
          settled = true;
          if (recognitionTimeout) clearTimeout(recognitionTimeout);
          const code = event.error || "speech_error";
          if ((code === "no-speech" || code === "audio-capture") && retries > 0) {
            voiceLog.textContent = "I did not catch that. Trying once more...";
            resolve(waitForSpeech(promptText, { retries: retries - 1, spokenPrompt, timeoutMs, allowSkip, emptyValue }));
            return;
          }
          if ((code === "no-speech" || code === "audio-capture") && allowSkip) {
            voiceLog.textContent = "No response captured. Marked as not required.";
            resolve(emptyValue);
            return;
          }
          reject(new Error(code));
        };
        recognition.onend = () => {
          recognitionBusy = false;
          const heard = finalTranscript.trim();
          if (allowSkip && heardSkipIntent(heard)) {
            settled = true;
            playBeep(740, 120);
            voiceLog.textContent = "Marked as not required.";
            resolve(emptyValue);
            return;
          }
          if (heard) {
            settled = true;
            playBeep(660, 120);
            voiceLog.textContent = `Heard: ${heard}`;
            resolve(heard);
            return;
          }
          if (!settled) {
            if (retries > 0) {
              voiceLog.textContent = "No speech captured. Trying again, please speak after the prompt.";
              resolve(waitForSpeech(promptText, { retries: retries - 1, spokenPrompt, timeoutMs, allowSkip, emptyValue }));
              return;
            }
            if (allowSkip) {
              voiceLog.textContent = "No response captured. Marked as not required.";
              resolve(emptyValue);
              return;
            }
            reject(new Error("no_speech_captured"));
          }
        };

        recognitionBusy = true;
        const startRecognition = () => {
          voiceLog.textContent = `${promptText} Listening now...`;
          window.setTimeout(() => {
            playBeep(900, 90);
            recognition.start();
          }, 80);
          recognitionTimeout = window.setTimeout(() => {
            try {
              recognition.stop();
            } catch (error) {
              // Ignore stop errors from already-ended sessions.
            }
          }, timeoutMs);
        };
        stopSpeechPlayback();
        if (spokenPrompt && promptText) {
          speak(promptText, { onend: startRecognition });
        } else {
          startRecognition();
        }
      });
    }

    async function startVoiceIntake() {
      if (!recognitionSupported) {
        voiceLog.textContent = "Voice intake needs a browser with speech recognition support.";
        return;
      }
      if (recognitionBusy) {
        voiceLog.textContent = "Voice assistant is already listening.";
        return;
      }

      try {
        stopSpeechPlayback();
        const name = await waitForSpeech("Tell me the customer name.", { retries: 0, timeoutMs: 4000 });
        document.getElementById("customerName").value = name;

        const employmentType = await waitForSpeech("Is the customer salaried, in business, or self-employed?", { retries: 0, timeoutMs: 4000 });
        document.getElementById("employmentType").value = parseEmploymentType(employmentType);

        const segmentAnswer = await waitForSpeech("Is this a residential or commercial lead?", { retries: 0, timeoutMs: 3500 });
        segmentSelect.value = parseSegment(segmentAnswer);
        syncSegmentFields();

        const location = await waitForSpeech("What is the preferred location?", { retries: 0, timeoutMs: 4000 });
        document.getElementById("location").value = inferLocation(location);

        const customerLocation = await waitForSpeech(
          "What is the customer's current pickup location? You can say skip or not required.",
          { retries: 0, timeoutMs: 5000, allowSkip: true, emptyValue: "" }
        );
        document.getElementById("customerLocation").value = heardSkipIntent(customerLocation) ? "" : inferLocation(customerLocation);

        const budget = await waitForSpeech("What is the budget?", { retries: 0, timeoutMs: 4000 });
        document.getElementById("budget").value = parseBudgetValue(budget);

        const timeline = await waitForSpeech("What is the timeline in days?", { retries: 0, timeoutMs: 3500 });
        document.getElementById("timelineDays").value = parseDaysValue(timeline);
        document.getElementById("profession").value = "";
        document.getElementById("totalExperienceYears").value = "";

        if (segmentSelect.value === "commercial") {
          const businessType = await waitForSpeech("What type of business is this lead for?", { retries: 0, timeoutMs: 4000 });
          document.getElementById("businessType").value = inferBusinessType(businessType);

          const sqftMin = await waitForSpeech("What is the minimum square footage required?", { retries: 0, timeoutMs: 3500 });
          document.getElementById("squareFeetMin").value = parseSquareFeetValue(sqftMin);

          const sqftMax = await waitForSpeech("What is the maximum square footage required?", { retries: 0, timeoutMs: 3500 });
          document.getElementById("squareFeetMax").value = parseSquareFeetValue(sqftMax);
        } else {
          const propertyType = await waitForSpeech("What property type does the customer want?", { retries: 0, timeoutMs: 4000 });
          document.getElementById("propertyType").value = inferResidentialPropertyType(propertyType);
        }

        const inquiry = await waitForSpeech("Now describe the inquiry in one sentence.", { retries: 0, timeoutMs: 5000 });
        document.getElementById("inquiry").value = cleanSpokenText(inquiry);
        applyVoiceIntelligence();
        document.getElementById("leadId").value = `voice_${segmentSelect.value}_${Date.now()}`;
        const finalMessage = "Thank you for the answers. I have captured the lead details and I am starting the workflow now.";
        voiceLog.textContent = finalMessage;
        playBeep(720, 150);
        await new Promise((resolve) => speak(finalMessage, { onend: resolve }));
        await runManualLead();
      } catch (error) {
        voiceLog.textContent = `Voice intake stopped: ${error.message}`;
      }
    }

    async function dictateInquiry() {
      if (!recognitionSupported) {
        voiceLog.textContent = "Voice dictation is not supported in this browser.";
        return;
      }
      if (recognitionBusy) {
        voiceLog.textContent = "Voice assistant is already listening.";
        return;
      }
      try {
        stopSpeechPlayback();
        const inquiry = await waitForSpeech("Please describe the customer inquiry.", { retries: 0, spokenPrompt: false, timeoutMs: 5000 });
        document.getElementById("inquiry").value = cleanSpokenText(inquiry);
        applyVoiceIntelligence();
        voiceLog.textContent = "Inquiry updated from voice input.";
      } catch (error) {
        voiceLog.textContent = `Dictation stopped: ${error.message}`;
      }
    }

    async function playLatestCall() {
      if (!playbackSupported) {
        voiceLog.textContent = "Speech playback is not supported in this browser.";
        return;
      }
      const response = await fetch("/calls/latest");
      const data = await response.json();
      if (!data.available || !data.call_transcript || !data.call_transcript.length) {
        voiceLog.textContent = "No call transcript is available yet. Run a lead through the workflow first.";
        return;
      }
      const script = data.call_transcript.map((turn) => `${turn.speaker}: ${turn.text}`).join(". ");
      voiceLog.textContent = `Playing latest call for ${data.customer_name}.`;
      speak(script);
    }

    async function submitTestInquiry() {
      const testText = testInquiryInput.value.trim();
      if (!testText) {
        testInputLog.textContent = "❌ Please enter an inquiry text.";
        return;
      }
      try {
        testInputLog.textContent = "⏳ Processing test inquiry...";
        document.getElementById("inquiry").value = cleanSpokenText(testText);
        document.getElementById("leadId").value = `test_${Date.now()}`;
        
        // Try to infer some basic fields from text patterns
        const textLower = testText.toLowerCase();
        if (textLower.includes("commercial") || textLower.includes("office") || textLower.includes("space")) {
          segmentSelect.value = "commercial";
          syncSegmentFields();
        } else {
          segmentSelect.value = "residential";
          syncSegmentFields();
        }
        
        // Try to parse budget if mentioned (look for numbers followed by crore/lakh/lac)
        const budgetMatch = testText.match(/(\d+)\s*(crore|lakh|lac)?/i);
        if (budgetMatch) {
          let amount = parseInt(budgetMatch[1]);
          if (budgetMatch[2]) {
            const unit = budgetMatch[2].toLowerCase();
            if (unit === "crore") amount = amount * 10000000;
            else if (unit === "lakh" || unit === "lac") amount = amount * 100000;
          }
          document.getElementById("budget").value = amount;
        }
        
        // Try to parse timeline from text
        const daysMatch = testText.match(/(\d+)\s*(?:day|week|month)/i);
        if (daysMatch) {
          let days = parseInt(daysMatch[1]);
          const unit = daysMatch[0].toLowerCase();
          if (unit.includes("week")) days = days * 7;
          else if (unit.includes("month")) days = days * 30;
          document.getElementById("timelineDays").value = Math.max(1, Math.min(365, days));
        }
        
        applyVoiceIntelligence();
        testInputLog.textContent = "✅ Test inquiry parsed successfully. Click submit to process the lead.";
        setTimeout(() => {
          testInputLog.textContent = "";
          testInquiryInput.value = "";
        }, 2000);
        await runManualLead();
      } catch (error) {
        testInputLog.textContent = `❌ Error: ${error.message}`;
      }
    }

    async function consumeStream(response) {
      console.log("[STREAM_START] Starting stream consumption");
      startButton.disabled = true;
      submitManualButton.disabled = true;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventCount = 0;

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) {
            console.log("[STREAM_DONE] Stream reading complete after " + eventCount + " events");
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const event = JSON.parse(line);
              eventCount++;
              console.log("[EVENT_" + eventCount + "] " + event.event + " (Lead: " + (event.lead_id || "N/A") + ")");
              addEventRow(event);

              if (event.event === "lead_received") {
                leads.set(event.lead_id, {
                  customer_name: event.payload.customer_name,
                  inquiry: event.payload.inquiry,
                  stage: "received",
                  segment: event.payload.segment || document.getElementById("segment").value
                });
                renderLeadCard(event.lead_id);
              }

              if (event.event === "lead_step") {
                const lead = leads.get(event.lead_id) || {};
                lead.grader_score = event.payload.grader_score;
                lead.stage = event.payload.last_action_result || lead.stage;
                if (event.payload.call_transcript && event.payload.call_transcript.length) {
                  const customerTurns = event.payload.call_transcript.filter((turn) => turn.speaker === "customer");
                  lead.last_contact_note = customerTurns.length ? customerTurns[customerTurns.length - 1].text : event.payload.call_outcome;
                }
                leads.set(event.lead_id, lead);
                renderLeadCard(event.lead_id);
                updateCabPanelFromPayload(event.payload, lead);
              }

              if (event.event === "lead_completed") {
                const lead = leads.get(event.lead_id) || {};
                lead.final_score = event.payload.final_score;
                lead.final_stage = event.payload.final_stage;
                leads.set(event.lead_id, lead);
                renderLeadCard(event.lead_id);
              }

              if (event.event === "run_completed") {
                statusText.textContent = "Completed " + event.payload.processed_leads + " simulated leads.";
                console.log("[RUN_COMPLETE] Run completed with " + event.payload.processed_leads + " leads");
              }
            } catch (parseErr) {
              console.error("[PARSE_ERROR] Failed to parse line:", line, parseErr);
            }
          }
        }
      } catch (streamErr) {
        console.error("[STREAM_ERROR] Stream error:", streamErr);
        statusText.textContent = "Stream error: " + streamErr.message;
      }

      startButton.disabled = false;
      submitManualButton.disabled = false;
      console.log("[REFRESH] Refreshing charts...");
      await fetchAndRenderConversionChart();
      await fetchAndRenderLeadCategorization();
      console.log("[REFRESH_DONE] Charts refreshed");
    }

    async function startStream() {
      try {
        console.log("[START] Start Stream clicked");
        resetBoards();
        statusText.textContent = "Streaming default CRM traffic...";
        console.log("[RESET] Resetting metrics...");
        // Reset backend metrics and categorization for new stream
        let metricsRes = await fetch("/metrics/reset", { method: "POST" });
        console.log("[METRICS] Metrics reset:", metricsRes.status);
        
        let categRes = await fetch("/lead-categorization/reset", { method: "POST" });
        console.log("[CATEGORY] Categorization reset:", categRes.status);
        
        console.log("[FETCH] Fetching stream...");
        const response = await fetch("/simulate/live/stream?delay_seconds=0.35");
        console.log("[STREAM] Stream fetch status:", response.status);
        
        if (!response.ok) {
          statusText.textContent = "Error: Stream failed with status " + response.status;
          throw new Error("Stream failed: " + response.status);
        }
        
        console.log("[CONSUME] Consuming stream...");
        await consumeStream(response);
        console.log("[SUCCESS] Stream completed successfully");
      } catch (error) {
        console.error("[ERROR] Error in startStream:", error);
        statusText.textContent = "Error: " + error.message;
        startButton.disabled = false;
        submitManualButton.disabled = false;
      }
    }

    async function runManualLead() {
      resetBoards();
      // Reset backend metrics and categorization for new stream
      await fetch("/metrics/reset", { method: "POST" });
      await fetch("/lead-categorization/reset", { method: "POST" });
      statusText.textContent = "Streaming manual lead...";
      const response = await fetch("/simulate/live/stream?delay_seconds=0.35", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(manualPayload())
      });
      await consumeStream(response);
    }

    async function fetchAndRenderConversionChart() {
      try {
        const response = await fetch("/metrics/conversions");
        const data = await response.json();
        const filter = segmentFilter ? segmentFilter.value : "all";
        
        // Prepare data based on filter with unified labels
        let chartData = {
          labels: ["Leads Received", "Contacted", "Qualified", "Engaged", "Deal Closed"],
          residential: null,
          commercial: null
        };
        
        let residentialData = data.residential;
        let commercialData = data.commercial;
        
        if (filter === "residential" || filter === "all") {
          chartData.residential = [
            residentialData.total_leads,
            residentialData.contacted,
            residentialData.interested_in_visit,
            residentialData.appointment_scheduled,
            residentialData.deal_closed
          ];
        }
        
        if (filter === "commercial" || filter === "all") {
          chartData.commercial = [
            commercialData.total_leads,
            commercialData.contacted,
            commercialData.proposal_sent,
            commercialData.negotiation,
            commercialData.deal_closed
          ];
        }
        
        // Update funnel metrics boxes
        updateFunnelMetrics(chartData, data);
        
        // Render chart
        renderConversionChart(chartData);
      } catch (error) {
        console.error("Error fetching conversion metrics:", error);
      }
    }

    function updateFunnelMetrics(chartData, data) {
      if (!funnelMetrics) return;
      funnelMetrics.innerHTML = "";
      const filter = segmentFilter ? segmentFilter.value : "all";
      
      if (filter === "residential" || filter === "all") {
        const residential = data.residential;
        const conversion = residential.total_leads > 0 ? (residential.deal_closed / residential.total_leads * 100).toFixed(1) : 0;
        
        funnelMetrics.innerHTML += `
          <div class="metric-box">
            <div class="label">Residential Leads</div>
            <div class="value">${residential.total_leads}</div>
          </div>
          <div class="metric-box">
            <div class="label">Residential Conversion Rate</div>
            <div class="value">${conversion}%</div>
          </div>
        `;
      }
      
      if (filter === "commercial" || filter === "all") {
        const commercial = data.commercial;
        const conversion = commercial.total_leads > 0 ? (commercial.deal_closed / commercial.total_leads * 100).toFixed(1) : 0;
        
        funnelMetrics.innerHTML += `
          <div class="metric-box">
            <div class="label">Commercial Leads</div>
            <div class="value">${commercial.total_leads}</div>
          </div>
          <div class="metric-box">
            <div class="label">Commercial Conversion Rate</div>
            <div class="value">${conversion}%</div>
          </div>
        `;
      }
    }

    function renderConversionChart(chartData) {
      const ctx = document.getElementById("conversionChart");
      if (!ctx || !chartData) return;
      const filter = segmentFilter ? segmentFilter.value : "all";
      
      const datasets = [];
      const colors = {
        residential: { bg: "rgba(13, 124, 102, 0.4)", border: "rgb(13, 124, 102)", fill: true },
        commercial: { bg: "rgba(183, 110, 43, 0.4)", border: "rgb(183, 110, 43)", fill: true }
      };
      
      if ((filter === "residential" || filter === "all") && chartData.residential) {
        datasets.push({
          label: "Residential Funnel",
          data: chartData.residential,
          borderColor: colors.residential.border,
          backgroundColor: colors.residential.bg,
          fill: colors.residential.fill,
          tension: 0.4,
          pointRadius: 5,
          pointHoverRadius: 7,
          borderWidth: 2,
          pointBackgroundColor: colors.residential.border,
          pointBorderColor: "white",
          pointBorderWidth: 2
        });
      }
      
      if ((filter === "commercial" || filter === "all") && chartData.commercial) {
        datasets.push({
          label: "Commercial Funnel",
          data: chartData.commercial,
          borderColor: colors.commercial.border,
          backgroundColor: colors.commercial.bg,
          fill: colors.commercial.fill,
          tension: 0.4,
          pointRadius: 5,
          pointHoverRadius: 7,
          borderWidth: 2,
          pointBackgroundColor: colors.commercial.border,
          pointBorderColor: "white",
          pointBorderWidth: 2
        });
      }
      
      if (conversionChart) {
        conversionChart.data.labels = chartData.labels;
        conversionChart.data.datasets = datasets;
        conversionChart.update();
      } else {
        conversionChart = new Chart(ctx, {
          type: "line",
          data: {
            labels: chartData.labels,
            datasets: datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: "top",
                labels: { font: { size: 12 }, padding: 15, usePointStyle: true }
              },
              tooltip: {
                backgroundColor: "rgba(0, 0, 0, 0.8)",
                titleFont: { size: 12 },
                bodyFont: { size: 11 },
                padding: 10,
                cornerRadius: 6
              }
            },
            scales: {
              y: {
                beginAtZero: true,
                ticks: { font: { size: 11 }, color: "rgb(94, 106, 107)" },
                grid: { color: "rgba(31, 44, 45, 0.1)" },
                title: { display: true, text: "Number of Leads" }
              },
              x: {
                ticks: { font: { size: 11 }, color: "rgb(94, 106, 107)" },
                grid: { display: false }
              }
            }
          }
        });
      }
    }

    async function resetConversionMetrics() {
      try {
        const response = await fetch("/metrics/reset", { method: "POST" });
        const data = await response.json();
        console.log(data.status);
        await fetchAndRenderConversionChart();
      } catch (error) {
        console.error("Error resetting metrics:", error);
      }
    }

    async function fetchAndRenderLeadCategorization() {
      try {
        const response = await fetch("/lead-categorization");
        const data = await response.json();
        
        // Render each category box
        const categories = [
          { key: "eligible_for_contact", label: "Eligible for Contact" },
          { key: "scheduled_for_visit", label: "Scheduled for Visit" },
          { key: "cold_leads", label: "Cold Leads" },
          { key: "qualification_pending", label: "Qualification Pending" },
          { key: "deal_closed", label: "Deal Closed" }
        ];
        
        categories.forEach(category => {
          const count = data[category.key] ? data[category.key].length : 0;
          const countEl = document.getElementById(`count-${category.key}`);
          const detailsEl = document.getElementById(`details-${category.key}`);
          
          if (countEl) {
            countEl.textContent = count;
          }
          
          if (detailsEl) {
            if (data[category.key] && data[category.key].length > 0) {
              const leadNames = data[category.key].map(lead => {
                const leadId = lead.lead_id || "unknown";
                const name = lead.customer_name || "N/A";
                const property = lead.property_type || "N/A";
                return `<div class="lead-item" style="font-size: 0.85rem; padding: 4px 0; color: var(--muted);">${name} (${property}, ${leadId})</div>`;
              }).join("");
              detailsEl.innerHTML = leadNames;
            } else {
              detailsEl.innerHTML = `<div class="lead-item" style="font-size: 0.85rem; padding: 4px 0; color: var(--muted);">No leads</div>`;
            }
          }
        });
      } catch (error) {
        console.error("Error fetching lead categorization:", error);
      }
    }

    async function fetchAndRenderMarketRates() {
      try {
        const response = await fetch("/market-rates");
        const data = await response.json();
        
        // Update the market rate title with current property type
        const segment = segmentSelect.value;
        const selectedPropertyType = segment === "residential" ? propertyTypeInput.value : businessTypeInput.value;
        const marketRateTitle = document.getElementById("marketRateTitle");
        if (marketRateTitle) {
          marketRateTitle.textContent = `Analyzing: ${selectedPropertyType || "Property"}`;
        }
        
        renderMarketRateChart(data.market_rates);
        updateMarketInfoGrid(data.market_rates);
      } catch (error) {
        console.error("Error fetching market rates:", error);
      }
    }

    function renderMarketRateChart(marketRates) {
      const ctx = document.getElementById("marketRateChart");
      if (!ctx || !marketRates) return;
      const locationFilter = marketLocationFilter ? marketLocationFilter.value : "all";
      const segment = segmentSelect ? segmentSelect.value : "residential";
      
      // Determine the property type to filter by
      let selectedPropertyType = segment === "residential" ? 
        (propertyTypeInput ? propertyTypeInput.value : "") : 
        (businessTypeInput ? businessTypeInput.value : "");
      
      // Normalize property type for matching
      const normalizePropertyType = (ptype) => {
        if (!ptype) return "";
        return ptype.toLowerCase().trim();
      };
      
      const targetPropertyType = normalizePropertyType(selectedPropertyType);
      
      const locations = [];
      const priceData = [];
      
      // Collect data only for the selected property type
      for (const [location, propertyTypes] of Object.entries(marketRates)) {
        if (locationFilter !== "all" && location !== locationFilter) continue;
        
        for (const [ptype, rates] of Object.entries(propertyTypes)) {
          if (normalizePropertyType(ptype) === targetPropertyType || ptype.toLowerCase().includes(targetPropertyType.split(" ")[0])) {
            locations.push(location);
            priceData.push(rates.average || 0);
            break; // Only add once per location for this property type
          }
        }
      }
      
      // If no specific property type found, show all available data
      if (priceData.length === 0) {
        for (const [location, propertyTypes] of Object.entries(marketRates)) {
          if (locationFilter !== "all" && location !== locationFilter) continue;
          
          for (const [ptype, rates] of Object.entries(propertyTypes)) {
            locations.push(`${location} - ${ptype}`);
            priceData.push(rates.average || 0);
          }
        }
      }
      
      const color = segment === "residential" ? 
        { bg: "rgba(13, 124, 102, 0.4)", border: "rgb(13, 124, 102)" } :
        { bg: "rgba(183, 110, 43, 0.4)", border: "rgb(183, 110, 43)" };
      
      const datasets = [{
        label: selectedPropertyType || "Market Rate",
        data: priceData,
        borderColor: color.border,
        backgroundColor: color.bg,
        fill: true,
        tension: 0.3,
        pointRadius: 5,
        pointHoverRadius: 7,
        borderWidth: 2,
        pointBackgroundColor: color.border,
        pointBorderColor: "white",
        pointBorderWidth: 2
      }];
      
      if (marketRateChart) {
        marketRateChart.data.labels = locations;
        marketRateChart.data.datasets = datasets;
        marketRateChart.update();
      } else {
        marketRateChart = new Chart(ctx, {
          type: "line",
          data: {
            labels: locations,
            datasets: datasets
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: "top",
                labels: { font: { size: 11 }, padding: 12, usePointStyle: true }
              },
              tooltip: {
                backgroundColor: "rgba(0, 0, 0, 0.8)",
                titleFont: { size: 11 },
                bodyFont: { size: 10 },
                padding: 10,
                cornerRadius: 6,
                callbacks: {
                  label: function(context) {
                    const value = context.parsed.y;
                    return context.dataset.label + ": ₹" + (value / 1000000).toFixed(2) + "M";
                  }
                }
              }
            },
            scales: {
              y: {
                beginAtZero: false,
                ticks: { font: { size: 10 }, color: "rgb(94, 106, 107)", callback: function(value) {
                  return "₹" + (value / 1000000).toFixed(1) + "M";
                }},
                grid: { color: "rgba(31, 44, 45, 0.1)" },
                title: { display: true, text: "Average Price" }
              },
              x: {
                ticks: { font: { size: 10 }, color: "rgb(94, 106, 107)" },
                grid: { display: false }
              }
            }
          }
        });
      }
    }
if (!marketInfoGrid) return;
      marketInfoGrid.innerHTML = "";
      const locationFilter = marketLocationFilter ? marketLocationFilter.value : "all";
      const segment = segmentSelect ? segmentSelect.value : "residential";
      
      // Determine the property type to filter by
      let selectedPropertyType = segment === "residential" ? 
        (propertyTypeInput ? propertyTypeInput.value : "") : 
        (businessTypeInput ? businessTypeInput.value : "")
      // Determine the property type to filter by
      let selectedPropertyType = segment === "residential" ? propertyTypeInput.value : businessTypeInput.value;
      const normalizePropertyType = (ptype) => {
        if (!ptype) return "";
        return ptype.toLowerCase().trim();
      };
      
      const targetPropertyType = normalizePropertyType(selectedPropertyType);
      
      // Show info only for the selected property type
      for (const [location, propertyTypes] of Object.entries(marketRates)) {
        if (locationFilter !== "all" && location !== locationFilter) continue;
        
        for (const [ptype, rates] of Object.entries(propertyTypes)) {
          // Match the property type
          if (normalizePropertyType(ptype) === targetPropertyType || 
              ptype.toLowerCase().includes(targetPropertyType.split(" ")[0])) {
            const avg = (rates.average / 1000000).toFixed(2);
            const min = (rates.min / 1000000).toFixed(2);
            const max = (rates.max / 1000000).toFixed(2);
            
            marketInfoGrid.innerHTML += `
              <div class="market-info-cell">
                <div class="loc">${location}</div>
                <div class="ptype">${ptype}</div>
                <div class="price">
                  Avg: ₹${avg}M<br/>
                  <span style="font-size: 0.75rem; color: var(--muted);">
                    (₹${min}M - ₹${max}M)
                  </span>
                </div>
              </div>
            `;
            break; // Only show once per location
          }
        }
      }
    }

    // Setup event listeners with null checks
    if (startButton) startButton.addEventListener("click", startStream);
    if (submitManualButton) submitManualButton.addEventListener("click", runManualLead);
    if (loadDefaultButton) loadDefaultButton.addEventListener("click", loadWhitefieldExample);
    if (loadCommercialButton) loadCommercialButton.addEventListener("click", loadCommercialExample);
    if (segmentSelect) {
      segmentSelect.addEventListener("change", () => {
        syncSegmentFields();
        fetchAndRenderMarketRates();
      });
    }
    if (startVoiceIntakeButton) startVoiceIntakeButton.addEventListener("click", startVoiceIntake);
    if (dictateInquiryButton) dictateInquiryButton.addEventListener("click", dictateInquiry);
    if (playLatestCallButton) playLatestCallButton.addEventListener("click", playLatestCall);
    if (submitTestInquiryButton) submitTestInquiryButton.addEventListener("click", submitTestInquiry);
    if (segmentFilter) segmentFilter.addEventListener("change", () => {
      fetchAndRenderConversionChart();
    });
    if (resetMetricsBtn) resetMetricsBtn.addEventListener("click", resetConversionMetrics);
    if (marketLocationFilter) marketLocationFilter.addEventListener("change", fetchAndRenderMarketRates);
    if (propertyTypeInput) {
      propertyTypeInput.addEventListener("change", fetchAndRenderMarketRates);
      propertyTypeInput.addEventListener("blur", fetchAndRenderMarketRates);
      propertyTypeInput.addEventListener("keyup", fetchAndRenderMarketRates);
    }
    if (businessTypeInput) {
      businessTypeInput.addEventListener("change", fetchAndRenderMarketRates);
      businessTypeInput.addEventListener("blur", fetchAndRenderMarketRates);
      businessTypeInput.addEventListener("keyup", fetchAndRenderMarketRates);
    }
    if (!recognitionSupported && !playbackSupported) {
      voiceLog.textContent = "Voice features are unavailable in this browser. Use Chrome or Edge for speech recognition.";
    } else if (!recognitionSupported) {
      voiceLog.textContent = "Voice playback is available, but microphone dictation is not supported in this browser.";
    
    // Initialize the dashboard
    console.log("Dashboard initializing...");
    (async function() {
      try {
        loadWhitefieldExample();
        console.log("Default example loaded");
      } catch (e) {
        console.error("Error loading default example:", e);
      }
      
      try {
        await fetchAndRenderConversionChart();
        console.log("Conversion chart rendered");
      } catch (e) {
        console.error("Error rendering conversion chart:", e);
      }
      
      try {
        await fetchAndRenderMarketRates();
        console.log("Market rates rendered");
      } catch (e) {
        console.error("Error rendering market rates:", e);
      }
      
      try {
        await fetchAndRenderLeadCategorization();
        console.log("Lead categorization rendered");
      } catch (e) {
        console.error("Error rendering lead categorization:", e);
      }
      console.log("Dashboard initialization complete");
    })();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


@app.get("/grader/{task_id}")
def grader(task_id: str) -> dict[str, object]:
    task = load_task(task_id)
    env.reset(task_id)
    current_state = env.state()
    return {"task_id": task_id, "score": grade_task(task, current_state)}
