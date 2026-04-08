from __future__ import annotations

import json

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

# Funnel metrics tracking
funnel_metrics = {
    "leads_received": 0,
    "contacted": 0,
    "qualified": 0,
    "engaged": 0,
    "deal_closed": 0,
    "purchased": 0,
}
lead_stages: dict[str, str] = {}  # Track each lead's current stage

# Market analysis data by location
market_data = {
    "Whitefield": {
        "residential": {"avg_price_per_sqft": 6500, "price_range": (5500, 7500), "demand": "high"},
        "commercial": {"avg_price_per_sqft": 8200, "price_range": (7000, 9500), "demand": "medium"}
    },
    "Marathahalli": {
        "residential": {"avg_price_per_sqft": 5800, "price_range": (5000, 6800), "demand": "high"},
        "commercial": {"avg_price_per_sqft": 7500, "price_range": (6500, 8800), "demand": "medium"}
    },
    "Sarjapur": {
        "residential": {"avg_price_per_sqft": 4500, "price_range": (3800, 5200), "demand": "medium"},
        "commercial": {"avg_price_per_sqft": 6000, "price_range": (5200, 7000), "demand": "low"}
    },
    "Indiranagar": {
        "residential": {"avg_price_per_sqft": 7200, "price_range": (6500, 8500), "demand": "very_high"},
        "commercial": {"avg_price_per_sqft": 9500, "price_range": (8500, 11000), "demand": "high"}
    },
    "Koramangala": {
        "residential": {"avg_price_per_sqft": 8500, "price_range": (7500, 10000), "demand": "very_high"},
        "commercial": {"avg_price_per_sqft": 11000, "price_range": (10000, 13000), "demand": "high"}
    },
    "HSR Layout": {
        "residential": {"avg_price_per_sqft": 7800, "price_range": (7000, 9000), "demand": "high"},
        "commercial": {"avg_price_per_sqft": 10000, "price_range": (9000, 12000), "demand": "medium"}
    },
    "MG Road": {
        "residential": {"avg_price_per_sqft": 9200, "price_range": (8500, 11000), "demand": "very_high"},
        "commercial": {"avg_price_per_sqft": 13000, "price_range": (12000, 15000), "demand": "very_high"}
    },
    "CBD Retail District": {
        "residential": {"avg_price_per_sqft": 7500, "price_range": (6800, 8800), "demand": "high"},
        "commercial": {"avg_price_per_sqft": 14000, "price_range": (12000, 16000), "demand": "very_high"}
    }
}

# Mock Property Database
property_data = {
    "res_prop_101": {
        "property_id": "res_prop_101",
        "title": "2BHK in Whitefield near metro",
        "location": "Whitefield",
        "segment": "residential",
        "price": 9200000,
        "details": {"property_type": "2BHK apartment", "bedrooms": 2, "builder_cab_available": True}
    },
    "res_prop_102": {
        "property_id": "res_prop_102",
        "title": "3BHK in Sarjapur",
        "location": "Sarjapur",
        "segment": "residential",
        "price": 11800000,
        "details": {"property_type": "3BHK apartment", "bedrooms": 3, "builder_cab_available": False}
    },
    "com_prop_301": {
        "property_id": "com_prop_301",
        "title": "Retail corner shell in CBD",
        "location": "CBD Retail District",
        "segment": "commercial",
        "price": 315000,
        "price_type": "lease",
        "details": {"square_feet": 2800, "fit_for": "retail_food", "frontage": "high"}
    },
    "res_prop_201": {
        "property_id": "res_prop_201",
        "title": "Modern 4BHK Villa in Indiranagar",
        "location": "Indiranagar",
        "segment": "residential",
        "price": 15000000,
        "details": {"property_type": "4BHK Villa", "bedrooms": 4, "builder_cab_available": True}
    },
    "com_prop_401": {
        "property_id": "com_prop_401",
        "title": "Premium Office Space in MG Road",
        "location": "MG Road",
        "segment": "commercial",
        "price": 250000,
        "price_type": "lease",
        "details": {"square_feet": 3500, "fit_for": "corporate", "frontage": "very_high"}
    }
}

# Mock Builder Database with Locations
builder_data = {
    "Whitefield": [
        {
            "name": "Prestige Group - Prestige Primrose",
            "location": "Whitefield, Bengaluru",
            "coordinate": "12.9698° N, 77.7499° E",
            "project_type": "Premium Residential",
            "units": "250+ Apartments"
        },
        {
            "name": "Lodha Group - Lodha Fiorenza",
            "location": "Whitefield Tech Hub Area",
            "coordinate": "12.9700° N, 77.7450° E",
            "project_type": "Ultra-Luxury Residential",
            "units": "180 Apartments"
        },
        {
            "name": "Sobha Limited - Sobha Plaza",
            "location": "Whitefield Central",
            "coordinate": "12.9705° N, 77.7505° E",
            "project_type": "Commercial/Residential Mix",
            "units": "150 Units"
        }
    ],
    "Marathahalli": [
        {
            "name": "Brigade Group - Brigade Lakefront",
            "location": "Marathahalli Main Road",
            "coordinate": "12.9540° N, 77.7260° E",
            "project_type": "Premium Residential",
            "units": "300+ Apartments"
        },
        {
            "name": "Godrej Properties - Godrej Garden City",
            "location": "Marathahalli South",
            "coordinate": "12.9530° N, 77.7250° E",
            "project_type": "Gated Community",
            "units": "500+ Villas & Apartments"
        },
        {
            "name": "Century Real Estate - Century Urban Heights",
            "location": "Marathahalli Outer Ring Road",
            "coordinate": "12.9520° N, 77.7270° E",
            "project_type": "Mid-Range Residential",
            "units": "200 Apartments"
        }
    ],
    "Sarjapur": [
        {
            "name": "Sattva Group - Sattva The Marvella",
            "location": "Sarjapur Road Tech Corridor",
            "coordinate": "12.8395° N, 77.7450° E",
            "project_type": "Emerging Luxury Residential",
            "units": "400+ Apartments"
        },
        {
            "name": "Ashton Global - Ashton Greens",
            "location": "Sarjapur Main",
            "coordinate": "12.8390° N, 77.7455° E",
            "project_type": "Green Living Community",
            "units": "280 Villas"
        },
        {
            "name": "Shriram Group - Shriram Summitt",
            "location": "Sarjapur Bangalore Development",
            "coordinate": "12.8400° N, 77.7460° E",
            "project_type": "Affordable Luxury",
            "units": "350 Apartments"
        }
    ],
    "Indiranagar": [
        {
            "name": "Mahindra Lifespaces - Mahindra Luminare",
            "location": "Indiranagar Premium Area",
            "coordinate": "13.0008° N, 77.6411° E",
            "project_type": "Ultra-Premium Residential",
            "units": "200 Villas"
        },
        {
            "name": "DLF Limited - DLF The Crest",
            "location": "Indiranagar Central",
            "coordinate": "13.0010° N, 77.6415° E",
            "project_type": "Luxury Apartments",
            "units": "180 Units"
        },
        {
            "name": "Tata Housing - Tata Primanti",
            "location": "Indiranagar East",
            "coordinate": "13.0015° N, 77.6420° E",
            "project_type": "Premium Gated Community",
            "units": "250 Apartments"
        }
    ],
    "Koramangala": [
        {
            "name": "Puravankara - Purva Valkyr",
            "location": "Koramangala 1st Block",
            "coordinate": "12.9352° N, 77.6245° E",
            "project_type": "Boutique Luxury",
            "units": "120 Apartments"
        },
        {
            "name": "Bengaluru Heritage - Forte",
            "location": "Koramangala Central",
            "coordinate": "12.9350° N, 77.6250° E",
            "project_type": "Commercial/Premium Residential",
            "units": "100 Units"
        },
        {
            "name": "Provident Housing - Provident Luxe",
            "location": "Koramangala Lifestyle Zone",
            "coordinate": "12.9355° N, 77.6240° E",
            "project_type": "Ultra-Luxury Residential",
            "units": "150 Apartments"
        }
    ],
    "HSR Layout": [
        {
            "name": "Merlin Group - Merlin Skycity",
            "location": "HSR Layout Landmark",
            "coordinate": "12.9272° N, 77.6345° E",
            "project_type": "Gated Premium Residential",
            "units": "280 Apartments"
        },
        {
            "name": "Casagrand - Casagrand Utopia",
            "location": "HSR Layout Extension",
            "coordinate": "12.9270° N, 77.6350° E",
            "project_type": "Mid-Premium Residential",
            "units": "200 Apartments"
        }
    ],
    "MG Road": [
        {
            "name": "Embassy Group - Embassy MG Road Plaza",
            "location": "MG Road Central Business District",
            "coordinate": "13.0004° N, 77.5939° E",
            "project_type": "Commercial/Office Spaces",
            "units": "500+ Sq.ft Commercial"
        },
        {
            "name": "K Raheja Corp - Raheja Residency",
            "location": "MG Road Premium Area",
            "coordinate": "13.0006° N, 77.5940° E",
            "project_type": "Corporate Housing",
            "units": "120 Premium Apartments"
        }
    ],
    "CBD Retail District": [
        {
            "name": "Pillar Group - Pillar Square",
            "location": "CBD Central",
            "coordinate": "13.0027° N, 77.5921° E",
            "project_type": "Commercial/Retail Premium",
            "units": "800+ Sq.ft Retail"
        },
        {
            "name": "Nexus Malls - Nexus Central",
            "location": "CBD Main Zone",
            "coordinate": "13.0025° N, 77.5925° E",
            "project_type": "Premium Retail/Commercial",
            "units": "1000+ Sq.ft Commercial"
        }
    ]
}

# Distance data (in km) between locations
distance_matrix = {
    "Whitefield": {"Marathahalli": 8.5, "Sarjapur": 12, "Indiranagar": 7, "Koramangala": 9.5, "HSR Layout": 11, "MG Road": 10, "CBD Retail District": 14},
    "Marathahalli": {"Whitefield": 8.5, "Sarjapur": 6, "Indiranagar": 4, "Koramangala": 7, "HSR Layout": 5, "MG Road": 5.5, "CBD Retail District": 9},
    "Sarjapur": {"Whitefield": 12, "Marathahalli": 6, "Indiranagar": 8, "Koramangala": 10, "HSR Layout": 9, "MG Road": 11, "CBD Retail District": 13},
    "Indiranagar": {"Whitefield": 7, "Marathahalli": 4, "Sarjapur": 8, "Koramangala": 3.5, "HSR Layout": 2, "MG Road": 1.5, "CBD Retail District": 5},
    "Koramangala": {"Whitefield": 9.5, "Marathahalli": 7, "Sarjapur": 10, "Indiranagar": 3.5, "HSR Layout": 4, "MG Road": 1.5, "CBD Retail District": 3},
    "HSR Layout": {"Whitefield": 11, "Marathahalli": 5, "Sarjapur": 9, "Indiranagar": 2, "Koramangala": 4, "MG Road": 3, "CBD Retail District": 6},
    "MG Road": {"Whitefield": 10, "Marathahalli": 5.5, "Sarjapur": 11, "Indiranagar": 1.5, "Koramangala": 1.5, "HSR Layout": 3, "CBD Retail District": 2},
    "CBD Retail District": {"Whitefield": 14, "Marathahalli": 9, "Sarjapur": 13, "Indiranagar": 5, "Koramangala": 3, "HSR Layout": 6, "MG Road": 2}
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


@app.get("/metrics/funnel")
def get_funnel_metrics() -> dict[str, object]:
    """Returns funnel metrics: leads received → contacted → qualified → engaged → deal closed → purchased"""
    return {
        "funnel_stages": funnel_metrics,
        "conversion_rates": {
            "contacted_rate": round((funnel_metrics["contacted"] / max(funnel_metrics["leads_received"], 1)) * 100, 1),
            "qualified_rate": round((funnel_metrics["qualified"] / max(funnel_metrics["contacted"], 1)) * 100, 1),
            "engaged_rate": round((funnel_metrics["engaged"] / max(funnel_metrics["qualified"], 1)) * 100, 1),
            "deal_closed_rate": round((funnel_metrics["deal_closed"] / max(funnel_metrics["engaged"], 1)) * 100, 1),
            "purchased_rate": round((funnel_metrics["purchased"] / max(funnel_metrics["deal_closed"], 1)) * 100, 1),
        }
    }


@app.post("/market-analysis")
def market_analysis(request: dict | None = None) -> dict[str, object]:
    """Returns market analysis and distance data based on location and segment"""
    location = request.get("location", "Whitefield") if request else "Whitefield"
    customer_location = request.get("customer_location", "Marathahalli") if request else "Marathahalli"
    segment = request.get("segment", "residential") if request else "residential"
    budget = request.get("budget") if request else None
    
    # Get market data for the location
    market_info = market_data.get(location, market_data["Whitefield"])
    segment_data = market_info.get(segment, market_info.get("residential", {}))
    
    # Get distance between locations
    distance = distance_matrix.get(customer_location, {}).get(location, 5.0)
    
    # Calculate affordable price range based on budget and market rates
    avg_price_per_sqft = segment_data.get("avg_price_per_sqft", 6500)
    market_range = segment_data.get("price_range", (5000, 8000))
    
    # Calculate max affordable area if budget is provided
    max_affordable_area = None
    if budget:
        max_affordable_area = budget / avg_price_per_sqft
    
    # Get comparable locations and their market rates
    comparable_locations = {}
    for loc, data in market_data.items():
        if loc != location:
            loc_segment_data = data.get(segment, data.get("residential", {}))
            distance_to_loc = distance_matrix.get(customer_location, {}).get(loc, 0)
            comparable_locations[loc] = {
                "avg_price_per_sqft": loc_segment_data.get("avg_price_per_sqft", 0),
                "demand": loc_segment_data.get("demand", "unknown"),
                "distance_km": distance_to_loc
            }
    
    return {
        "location": location,
        "segment": segment,
        "customer_location": customer_location,
        "distance_km": distance,
        "market_rate": {
            "avg_price_per_sqft": avg_price_per_sqft,
            "price_range": market_range,
            "demand": segment_data.get("demand", "medium")
        },
        "budget_analysis": {
            "budget": budget,
            "max_affordable_area_sqft": round(max_affordable_area, 1) if max_affordable_area else None,
            "price_vs_market": round((budget / (avg_price_per_sqft * 1500) * 100) - 100, 1) if budget else None
        },
        "comparable_locations": comparable_locations
    }


@app.get("/properties/{property_id}")
def get_property_details(property_id: str) -> dict[str, object]:
    """Returns details for a specific property with builder info and market insights"""
    prop = property_data.get(property_id, {})
    if not prop:
        return {"error": "Property not found", "property_id": property_id}
    
    # Get builder info for this property's location
    location = prop.get("location")
    builder_info = get_builder_info_for_location(location) if location else None
    
    # Calculate price per sqft if applicable
    price_per_sqft = None
    details = prop.get("details", {})
    if details.get("square_feet") and prop.get("price"):
        price_per_sqft = round(prop["price"] / details["square_feet"], 0)
    
    return {
        **prop,
        "builder_info": builder_info,
        "price_per_sqft": price_per_sqft,
        "market_rate": market_data.get(location, {}).get(prop.get("segment"), {}).get("avg_price_per_sqft")
    }

@app.get("/builders/by-location/{location}")
def get_builders_by_location(location: str) -> dict[str, object]:
    """Returns list of builders in a specific location"""
    builders = builder_data.get(location, [])
    return {
        "location": location,
        "builder_count": len(builders),
        "builders": builders
    }


@app.get("/builders/search")
def search_builders(location: str = None, project_type: str = None) -> dict[str, object]:
    """Search builders by location and/or project type"""
    results = []
    
    for loc, builders in builder_data.items():
        if location and location.lower() not in loc.lower():
            continue
        
        for builder in builders:
            if project_type and project_type.lower() not in builder["project_type"].lower():
                continue
            results.append({
                "location": loc,
                **builder
            })
    
    return {
        "search_criteria": {"location": location, "project_type": project_type},
        "results_count": len(results),
        "results": results
    }


def get_builder_info_for_location(location: str) -> dict | None:
    """Helper function to get primary builder information for a location"""
    builders = builder_data.get(location, [])
    if builders:
        return builders[0]  # Return first/primary builder
    return None


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
    for raw_event in stream:
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            yield raw_event
            continue

        payload = event.get("payload", {})
        lead_id = event.get("lead_id")
        event_type = event.get("event")

        # Track funnel metrics
        if event_type == "lead_received":
            funnel_metrics["leads_received"] += 1
            lead_stages[lead_id] = "received"
        
        elif event_type == "lead_step":
            current_stage = lead_stages.get(lead_id, "received")
            last_action = payload.get("last_action_result", "")
            
            # Update stage based on action result
            if last_action and current_stage != last_action:
                # Prevent double-counting by checking if we're moving to a new stage
                stage_order = ["received", "contacted", "qualified", "engaged", "deal_closed", "purchased"]
                if last_action in stage_order:
                    old_index = stage_order.index(current_stage) if current_stage in stage_order else 0
                    new_index = stage_order.index(last_action)
                    
                    # Increment metrics for each stage reached
                    if new_index > old_index:
                        for idx in range(old_index + 1, new_index + 1):
                            stage = stage_order[idx]
                            if stage == "contacted" and funnel_metrics["contacted"] == funnel_metrics.get("_contacted_count", 0):
                                funnel_metrics["contacted"] += 1
                                funnel_metrics["_contacted_count"] = funnel_metrics["contacted"]
                            elif stage == "qualified" and current_stage in ["received", "contacted"]:
                                funnel_metrics["qualified"] += 1
                            elif stage == "engaged" and current_stage in ["received", "contacted", "qualified"]:
                                funnel_metrics["engaged"] += 1
                            elif stage == "deal_closed" and current_stage in ["received", "contacted", "qualified", "engaged"]:
                                funnel_metrics["deal_closed"] += 1
                    lead_stages[lead_id] = last_action
            
            if payload.get("call_transcript"):
                latest_call_cache.clear()
                latest_call_cache.update(
                    {
                        "opportunity_id": lead_id,
                        "customer_name": payload.get("customer_name") or lead_id,
                        "available": True,
                        "customer_contacted": True,
                        "call_outcome": payload.get("call_outcome"),
                        "last_contact_note": _last_customer_turn(payload.get("call_transcript", [])),
                        "call_transcript": payload.get("call_transcript", []),
                    }
                )
        
        elif event_type == "lead_completed":
            final_stage = payload.get("final_stage", "")
            if final_stage == "deal_closed":
                funnel_metrics["deal_closed"] += 1
            lead_stages[lead_id] = "completed"
        
        elif event_type == "run_completed":
            # Reset on new run
            funnel_metrics["leads_received"] = payload.get("processed_leads", 0)
        
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
    .fallback-text-panel {
      border: 2px solid var(--accent);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
      background: linear-gradient(135deg, rgba(13, 124, 102, 0.08) 0%, rgba(210, 180, 222, 0.08) 100%);
      box-shadow: 0 4px 12px rgba(13, 124, 102, 0.1);
    }
    .fallback-text-panel strong {
      color: var(--accent);
      display: block;
      margin-bottom: 8px;
    }
    .fallback-question {
      color: var(--ink);
      font-size: 0.95rem;
      margin-bottom: 12px;
      font-weight: 600;
      padding: 8px 0;
    }
    .fallback-input-group {
      display: grid;
      grid-template-columns: 1fr 120px;
      gap: 8px;
      margin-bottom: 10px;
    }
    .fallback-input-group input {
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.95rem;
      background: white;
      color: var(--ink);
    }
    .fallback-input-group input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(13, 124, 102, 0.1);
    }
    .fallback-input-group button {
      padding: 10px 12px;
      font-size: 0.9rem;
      cursor: pointer;
      border-radius: 8px;
      border: none;
    }
    #fallbackSubmitButton {
      background: var(--accent);
      color: white;
      font-weight: 600;
    }
    #fallbackSubmitButton:hover {
      background: #0a9d80;
    }
    #fallbackSkipButton {
      grid-column: 2;
      background: #ccc;
      color: #333;
      font-weight: 500;
    }
    #fallbackSkipButton:hover {
      background: #bbb;
    }
    .fallback-status {
      font-size: 0.85rem;
      color: var(--muted);
      padding: 6px 0;
      min-height: 18px;
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
    .chart-container {
      position: relative;
      width: 100%;
      height: 420px;
      margin-bottom: 18px;
    }
    .funnel-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 24px;
    }
    .chart-section {
      border: 1px solid var(--border);
      background: var(--panel);
      backdrop-filter: blur(16px);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 18px;
    }
    .funnel-stage {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      padding: 16px;
      background: rgba(245, 250, 248, 0.9);
      border-radius: 12px;
      border: 1px solid var(--accent-soft);
      margin-bottom: 10px;
    }
    .funnel-stage-label {
      font-weight: 700;
      color: var(--accent);
      font-size: 0.95rem;
    }
    .funnel-stage-count {
      font-size: 1.8rem;
      color: var(--ink);
      font-weight: 700;
    }
    .funnel-stage-rate {
      font-size: 0.85rem;
      color: var(--muted);
    }
    .market-analysis-grid {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 18px;
      margin-bottom: 24px;
    }
    .market-chart-container {
      position: relative;
      width: 100%;
      height: 380px;
      margin-bottom: 18px;
    }
    .market-metrics-panel {
      display: grid;
      gap: 12px;
    }
    .metric-card {
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      background: rgba(216, 239, 232, 0.4);
      border-left: 4px solid var(--accent);
    }
    .metric-label {
      font-size: 0.85rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
    }
    .metric-value {
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--ink);
    }
    .metric-subtext {
      font-size: 0.8rem;
      color: var(--muted);
      margin-top: 4px;
    }
    .comparable-locations {
      border: 1px solid var(--border);
      background: var(--panel);
      backdrop-filter: blur(16px);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 18px;
      margin-bottom: 24px;
    }
    .location-row {
      display: grid;
      grid-template-columns: 150px 1.5fr 100px auto auto;
      gap: 1rem;
      padding: 1.2rem;
      margin-bottom: 10px;
      background: linear-gradient(to right, rgba(13, 124, 102, 0.05), rgba(255, 255, 255, 0.5));
      border-radius: 12px;
      border-left: 4px solid var(--accent);
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent);
      align-items: center;
      transition: all 0.2s ease;
    }
    .location-row:hover {
      background: linear-gradient(to right, rgba(13, 124, 102, 0.1), rgba(255, 255, 255, 0.6));
      box-shadow: 0 2px 8px rgba(13, 124, 102, 0.1);
    }
    .location-name {
      font-weight: 700;
      color: var(--ink);
      min-width: 140px;
    }
    .location-segment-info {
      color: var(--medium-ink);
      font-size: 0.95rem;
    }
    .location-segment-info strong {
      color: var(--accent);
    }
    .location-rate {
      color: var(--accent);
      font-size: 0.95rem;
    }
    .location-distance {
      color: var(--muted);
      font-size: 0.9rem;
      text-align: right;
    }
    .demand-badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 600;
      text-transform: capitalize;
    }
    .demand-very_high {
      background: #fdd835;
      color: #333;
    }
    .demand-high {
      background: #4caf50;
      color: white;
    }
    .demand-medium {
      background: #2196f3;
      color: white;
    }
    .demand-low {
      background: #9e9e9e;
      color: white;
    }
    .location-affordability {
      color: var(--medium-ink);
      font-size: 0.9rem;
      white-space: nowrap;
      text-align: right;
    }
    .location-demand {
      font-weight: 500;
      text-align: center;
      padding: 4px 8px !important;
      border-radius: 4px !important;
      font-size: 0.75rem !important;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
      .market-analysis-grid { grid-template-columns: 1fr; }
      .location-row { grid-template-columns: 1fr; }
      h1 { max-width: none; }
      .form-grid { grid-template-columns: 1fr; }
    }
    .builder-search-panel {
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      background: rgba(245, 245, 250, 0.9);
      margin-bottom: 18px;
    }
    .builder-results {
      margin-top: 16px;
      display: grid;
      gap: 12px;
    }
    .builder-card {
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.9);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
    }
    .builder-card h3 {
      margin: 0 0 8px 0;
      font-size: 1rem;
      color: var(--ink);
    }
    .builder-card p {
      margin: 4px 0;
      font-size: 0.92rem;
      color: var(--medium-ink);
    }
    .builder-info-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 8px;
      font-size: 0.88rem;
    }
    .builder-info-item {
      padding: 6px 8px;
      background: rgba(13, 124, 102, 0.06);
      border-radius: 8px;
      border-left: 3px solid var(--accent);
    }
    .builder-info-label {
      color: var(--muted);
      font-size: 0.8rem;
      font-weight: 600;
      text-transform: uppercase;
      margin-bottom: 2px;
    }
    .builder-info-value {
      color: var(--ink);
      font-weight: 500;
    }
    .builder-empty-state {
      text-align: center;
      padding: 24px 16px;
      color: var(--muted);
      font-size: 0.95rem;
    }
    .property-recommendation {
      background: linear-gradient(135deg, rgba(13, 124, 102, 0.08) 0%, rgba(210, 180, 222, 0.06) 100%);
      border: 1px solid rgba(13, 124, 102, 0.2);
      border-radius: 12px;
      padding: 12px;
      margin: 10px 0;
    }
    .property-header {
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 10px;
      font-size: 0.95rem;
    }
    .property-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .property-item {
      padding: 8px;
      background: rgba(255, 255, 255, 0.6);
      border-radius: 8px;
      border-left: 3px solid var(--accent);
    }
    .property-label {
      font-size: 0.75rem;
      color: var(--muted);
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 2px;
    }
    .property-value {
      font-size: 0.92rem;
      color: var(--ink);
      font-weight: 600;
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
    <div class="funnel-grid">
      <div class="chart-section">
        <h2>Business Funnel: Lead to Purchase</h2>
        <div class="chart-container">
          <canvas id="funnelChart"></canvas>
        </div>
      </div>
      <div class="chart-section">
        <h2>Conversion Rates by Stage</h2>
        <div id="conversionMetrics">
          <div class="funnel-stage">
            <div class="funnel-stage-label">Leads Received → Contacted</div>
            <div class="funnel-stage-count" id="rate1">0%</div>
          </div>
          <div class="funnel-stage">
            <div class="funnel-stage-label">Contacted → Qualified</div>
            <div class="funnel-stage-count" id="rate2">0%</div>
          </div>
          <div class="funnel-stage">
            <div class="funnel-stage-label">Qualified → Engaged</div>
            <div class="funnel-stage-count" id="rate3">0%</div>
          </div>
          <div class="funnel-stage">
            <div class="funnel-stage-label">Engaged → Deal Closed</div>
            <div class="funnel-stage-count" id="rate4">0%</div>
          </div>
          <div class="funnel-stage">
            <div class="funnel-stage-label">Deal Closed → Purchased</div>
            <div class="funnel-stage-count" id="rate5">0%</div>
          </div>
        </div>
      </div>
    </div>
    <div class="market-analysis-grid">
      <div class="chart-section">
        <h2><span id="analysisLocationLabel">Whitefield</span> Market Analysis & Comparable Locations</h2>
        <div style="color: var(--medium-ink); font-size: 0.85rem; margin-bottom: 12px;">
          <span id="analysisSegmentLabel">Residential</span> segment pricing
        </div>
        <div class="market-chart-container">
          <canvas id="marketChart"></canvas>
        </div>
      </div>
      <div class="market-metrics-panel">
        <h2 style="margin: 0 0 12px;">Key Metrics</h2>
        <div class="metric-card">
          <div class="metric-label">Distance to Site</div>
          <div class="metric-value" id="distanceValue">-</div>
          <div class="metric-subtext">km from customer location</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Avg Market Rate</div>
          <div class="metric-value" id="marketRateValue">-</div>
          <div class="metric-subtext">per sq.ft in this area</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Market Demand</div>
          <div id="demandBadge" style="margin-top: 8px;"></div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Max Affordable Area</div>
          <div class="metric-value" id="maxAreaValue">-</div>
          <div class="metric-subtext">based on your budget</div>
        </div>
      </div>
    </div>
    <div class="comparable-locations">
      <h2>Comparable Locations</h2>
      <div style="color: var(--medium-ink); font-size: 0.9rem; margin-bottom: 1rem;">
        <span id="segmentLabel">Residential</span> properties | 
        <span>Sorted by distance from <strong id="customerLocationLabel">Marathahalli</strong></span>
      </div>
      <div id="comparableLocationsList"></div>
    </div>
    <div class="grid">
      <section>
        <h2>Manual Lead Entry</h2>
        <div class="voice-panel">
          <div><strong>Voice Assistant</strong></div>
          <div class="sub">Use your microphone to capture a lead verbally or play back the latest simulated call flow. Best supported in Chromium-based browsers.</div>
          <div class="form-actions" style="margin-top: 12px; margin-bottom: 0;">
            <button id="startVoiceIntakeButton" class="voice">Start Voice Intake</button>
            <button id="dictateInquiryButton" class="voice">Dictate Inquiry</button>
            <button id="playLatestCallButton" class="secondary">Play Latest Call</button>
          </div>
          <div class="voice-log" id="voiceLog">Voice assistant idle.</div>
        </div>
        <div id="fallbackTextInputPanel" class="fallback-text-panel" style="display: none;">
          <div><strong>Text Input Fallback</strong></div>
          <div id="fallbackQuestionText" class="fallback-question"></div>
          <div class="fallback-input-group">
            <input id="fallbackTextInput" type="text" placeholder="Type your answer here..." />
            <button id="fallbackSubmitButton" class="voice">Submit</button>
            <button id="fallbackSkipButton" class="secondary" style="display: none;">Skip (if optional)</button>
          </div>
          <div id="fallbackStatus" class="fallback-status"></div>
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
              <option value="residential" selected>Residential</option>
              <option value="commercial">Commercial</option>
            </select>
          </label>
          <label>
            Property Location
            <select id="location">
              <option value="Whitefield" selected>Whitefield - Tech Hub</option>
              <option value="Marathahalli">Marathahalli - Popular</option>
              <option value="Sarjapur">Sarjapur - Emerging</option>
              <option value="Indiranagar">Indiranagar - Premium</option>
              <option value="Koramangala">Koramangala - Luxury</option>
              <option value="HSR Layout">HSR Layout - Premium</option>
              <option value="MG Road">MG Road - Ultra-Premium</option>
              <option value="CBD Retail District">CBD Retail District - Commercial Hub</option>
            </select>
          </label>
          <label>
            Your Current Location
            <select id="customerLocation">
              <option value="Marathahalli" selected>Marathahalli - Popular</option>
              <option value="Whitefield">Whitefield - Tech Hub</option>
              <option value="Sarjapur">Sarjapur - Emerging</option>
              <option value="Indiranagar">Indiranagar - Premium</option>
              <option value="Koramangala">Koramangala - Luxury</option>
              <option value="HSR Layout">HSR Layout - Premium</option>
              <option value="MG Road">MG Road - Ultra-Premium</option>
              <option value="CBD Retail District">CBD Retail District - Commercial Hub</option>
            </select>
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
        <h2>Builder Search</h2>
        <div class="builder-search-panel">
          <div class="sub">Search and explore builders/projects available in your preferred location.</div>
          <div class="form-grid" style="margin-top: 12px;">
            <label>
              Search Location
              <select id="builderSearchLocation">
                <option value="">Select a location...</option>
                <option value="Whitefield">Whitefield - Tech Hub</option>
                <option value="Marathahalli">Marathahalli - Popular</option>
                <option value="Sarjapur">Sarjapur - Emerging</option>
                <option value="Indiranagar">Indiranagar - Premium</option>
                <option value="Koramangala">Koramangala - Luxury</option>
                <option value="HSR Layout">HSR Layout - Premium</option>
                <option value="MG Road">MG Road - Ultra-Premium</option>
                <option value="CBD Retail District">CBD Retail District - Commercial Hub</option>
              </select>
            </label>
            <label>
              Project Type (Optional)
              <select id="builderSearchType">
                <option value="">All types</option>
                <option value="Residential">Residential</option>
                <option value="Commercial">Commercial</option>
                <option value="Mix">Mix</option>
              </select>
            </label>
          </div>
          <div class="form-actions">
            <button id="searchBuildersButton" class="voice">Search Builders</button>
          </div>
          <div id="builderSearchResults" class="builder-results"></div>
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
    const fallbackTextInputPanel = document.getElementById("fallbackTextInputPanel");
    const fallbackQuestionText = document.getElementById("fallbackQuestionText");
    const fallbackTextInput = document.getElementById("fallbackTextInput");
    const fallbackSubmitButton = document.getElementById("fallbackSubmitButton");
    const fallbackSkipButton = document.getElementById("fallbackSkipButton");
    const fallbackStatus = document.getElementById("fallbackStatus");
    const leads = new Map();
    const cabVoiceState = new Map();
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const recognitionSupported = Boolean(SpeechRecognition);
    const playbackSupported = Boolean(window.speechSynthesis);
    let recognitionBusy = false;

    // Funnel chart variables
    let funnelChartInstance = null;
    const funnelCtx = document.getElementById("funnelChart")?.getContext("2d");

    // Market analysis chart variables
    let marketChartInstance = null;
    const marketCtx = document.getElementById("marketChart")?.getContext("2d");

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
      
      // Build property recommendation section
      let propertyHTML = "";
      if (lead.property_details) {
        const prop = lead.property_details;
        const builder = prop.builder_info;
        const marketRate = prop.market_rate;
        const pricePerSqft = prop.price_per_sqft;
        
        propertyHTML = `
          <div class="property-recommendation">
            <div class="property-header">✓ Recommended Property Details</div>
            <div class="property-grid">
              <div class="property-item">
                <div class="property-label">Property</div>
                <div class="property-value">${prop.title}</div>
              </div>
              <div class="property-item">
                <div class="property-label">Location</div>
                <div class="property-value">${prop.location}</div>
              </div>
              ${builder ? `
              <div class="property-item">
                <div class="property-label">Builder</div>
                <div class="property-value">${builder.name}</div>
              </div>
              ` : ""}
              <div class="property-item">
                <div class="property-label">Price</div>
                <div class="property-value">₹${(prop.price / 100000).toFixed(1)}L</div>
              </div>
              ${pricePerSqft ? `
              <div class="property-item">
                <div class="property-label">Rate/SqFt</div>
                <div class="property-value">₹${pricePerSqft}</div>
              </div>
              ` : ""}
              ${marketRate ? `
              <div class="property-item">
                <div class="property-label">Market Rate</div>
                <div class="property-value">₹${marketRate}</div>
              </div>
              ` : ""}
              ${lead.distance_to_property ? `
              <div class="property-item">
                <div class="property-label">Distance</div>
                <div class="property-value">${lead.distance_to_property} km</div>
              </div>
              ` : ""}
            </div>
          </div>
        `;
      }
      
      card.innerHTML = `
        <div class="lead-meta">
          <strong>${lead.customer_name || leadId}</strong>
          <span>${leadId}</span>
        </div>
        <div>${lead.inquiry || ""}</div>
        ${lead.last_contact_note ? `<div class="score">Call Note: ${lead.last_contact_note}</div>` : ""}
        ${propertyHTML}
        <div class="score">Stage: ${lead.final_stage || lead.stage || "receiving"} | Score: ${lead.final_score ?? lead.grader_score ?? 0}</div>
      `;
    }

    function addEventRow(event) {
      const row = document.createElement("div");
      row.className = "event-row";
      row.innerHTML = `<div class="event-tag">${event.event}</div><pre>${JSON.stringify(event, null, 2)}</pre>`;
      eventList.prepend(row);
    }

    function fetchAndRenderFunnelChart() {
      fetch("/metrics/funnel")
        .then((response) => response.json())
        .then((data) => {
          const stages = data.funnel_stages || {};
          const rates = data.conversion_rates || {};
          
          // Update conversion rate display
          document.getElementById("rate1").textContent = rates.contacted_rate + "%";
          document.getElementById("rate2").textContent = rates.qualified_rate + "%";
          document.getElementById("rate3").textContent = rates.engaged_rate + "%";
          document.getElementById("rate4").textContent = rates.deal_closed_rate + "%";
          document.getElementById("rate5").textContent = rates.purchased_rate + "%";
          
          // Render funnel chart
          if (funnelCtx && stages.leads_received > 0) {
            const labels = ["Leads Received", "Contacted", "Qualified", "Engaged", "Deal Closed", "Purchased"];
            const values = [
              stages.leads_received,
              stages.contacted,
              stages.qualified,
              stages.engaged,
              stages.deal_closed,
              stages.purchased || 0
            ];
            
            // Create funnel effect by calculating widths
            const maxValue = Math.max(...values, 1);
            
            if (funnelChartInstance) {
              funnelChartInstance.destroy();
            }
            
            funnelChartInstance = new Chart(funnelCtx, {
              type: "bar",
              data: {
                labels: labels,
                datasets: [
                  {
                    label: "Leads Count",
                    data: values,
                    backgroundColor: [
                      "rgba(13, 124, 102, 0.8)",
                      "rgba(13, 124, 102, 0.75)",
                      "rgba(13, 124, 102, 0.65)",
                      "rgba(13, 124, 102, 0.55)",
                      "rgba(13, 124, 102, 0.45)",
                      "rgba(13, 124, 102, 0.35)"
                    ],
                    borderColor: "rgba(13, 124, 102, 1)",
                    borderWidth: 2,
                    borderRadius: 8
                  }
                ]
              },
              options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: {
                    display: false
                  },
                  tooltip: {
                    enabled: true,
                    callbacks: {
                      label: function(context) {
                        return "Count: " + context.parsed.x;
                      }
                    }
                  }
                },
                scales: {
                  x: {
                    beginAtZero: true,
                    max: maxValue * 1.1,
                    grid: {
                      color: "rgba(31, 44, 45, 0.08)"
                    }
                  },
                  y: {
                    grid: {
                      display: false
                    }
                  }
                }
              }
            });
          }
        })
        .catch((error) => console.error("[FUNNEL_CHART] Error fetching metrics:", error));
    }

    function fetchAndRenderMarketAnalysis() {
      const location = document.getElementById("location").value || "Whitefield";
      const customerLocation = document.getElementById("customerLocation").value || "Marathahalli";
      const segment = document.getElementById("segment").value || "residential";
      const budget = parseInt(document.getElementById("budget").value) || null;
      
      const payload = {
        location,
        customer_location: customerLocation,
        segment,
        budget
      };
      
      fetch("/market-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
        .then((response) => response.json())
        .then((data) => {
          console.log("[MARKET_ANALYSIS] Data received:", data);
          
          // Update segment and location labels
          document.getElementById("segmentLabel").textContent = data.segment.charAt(0).toUpperCase() + data.segment.slice(1);
          document.getElementById("customerLocationLabel").textContent = data.customer_location;
          document.getElementById("analysisLocationLabel").textContent = data.location;
          document.getElementById("analysisSegmentLabel").textContent = data.segment.charAt(0).toUpperCase() + data.segment.slice(1);
          
          // Update key metrics
          document.getElementById("distanceValue").textContent = data.distance_km.toFixed(1);
          document.getElementById("marketRateValue").textContent = "₹" + data.market_rate.avg_price_per_sqft.toLocaleString();
          
          const demandBadge = document.getElementById("demandBadge");
          const demand = data.market_rate.demand.toLowerCase().replace(/_/g, "_");
          demandBadge.innerHTML = `<span class="demand-badge demand-${demand}" style="text-transform: capitalize;">${data.market_rate.demand.replace(/_/g, " ")}</span>`;
          
          if (data.budget_analysis.max_affordable_area_sqft) {
            document.getElementById("maxAreaValue").textContent = data.budget_analysis.max_affordable_area_sqft.toLocaleString() + " sq.ft";
          } else {
            document.getElementById("maxAreaValue").textContent = "-";
          }
          
          // Render comparable locations chart
          if (marketCtx && data.comparable_locations) {
            const locations = [];
            const rates = [];
            const distances = [];
            
            Object.entries(data.comparable_locations).forEach(([loc, info]) => {
              locations.push(loc);
              rates.push(info.avg_price_per_sqft);
              distances.push(info.distance_km);
            });
            
            if (marketChartInstance) {
              marketChartInstance.destroy();
            }
            
            marketChartInstance = new Chart(marketCtx, {
              type: "bubble",
              data: {
                datasets: [
                  {
                    label: "Comparable Locations (Price vs Distance)",
                    data: locations.map((loc, idx) => ({
                      x: distances[idx],
                      y: rates[idx],
                      r: 15
                    })),
                    backgroundColor: "rgba(13, 124, 102, 0.6)",
                    borderColor: "rgba(13, 124, 102, 1)",
                    borderWidth: 2
                  }
                ]
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: {
                    display: false
                  },
                  tooltip: {
                    enabled: true,
                    callbacks: {
                      label: function(context) {
                        const idx = context.dataIndex;
                        const loc = locations[idx];
                        return loc + " - ₹" + rates[idx] + "/sqft @ " + distances[idx] + " km";
                      }
                    }
                  }
                },
                scales: {
                  x: {
                    title: {
                      display: true,
                      text: "Distance from Customer Location (km)"
                    },
                    min: 0,
                    grid: { color: "rgba(31, 44, 45, 0.08)" }
                  },
                  y: {
                    title: {
                      display: true,
                      text: "Market Rate (₹/sqft)"
                    },
                    min: 0,
                    grid: { color: "rgba(31, 44, 45, 0.08)" }
                  }
                }
              }
            });
          }
          
          // Render comparable locations list sorted by distance
          const sortedLocations = Object.entries(data.comparable_locations)
            .sort(([,a], [,b]) => a.distance_km - b.distance_km);
          
          const listHtml = sortedLocations
            .map(([loc, info]) => {
              const demandColor = {
                'very_high': '#fdd835',
                'high': '#4caf50',
                'medium': '#2196f3',
                'low': '#9e9e9e'
              }[info.demand.toLowerCase()] || '#9e9e9e';
              
              const affordability = data.budget_analysis.max_affordable_area_sqft 
                ? ((data.budget_analysis.max_affordable_area_sqft * info.avg_price_per_sqft) / data.budget_analysis.budget * 100).toFixed(0)
                : null;
              
              const affordabilityText = affordability 
                ? affordability + '% of budget'  
                : 'Budget: N/A';
              
              return `
                <div class="location-row" style="border-left: 4px solid ${demandColor};">
                  <div class="location-name">${loc}</div>
                  <div class="location-segment-info">
                    <strong>${data.segment.charAt(0).toUpperCase() + data.segment.slice(1)}</strong> | 
                    ₹${info.avg_price_per_sqft.toLocaleString()}/sqft
                  </div>
                  <div class="location-distance">${info.distance_km} km</div>
                  <div class="location-affordability">${affordabilityText}</div>
                  <div class="location-demand" style="background: ${demandColor}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;">
                    ${info.demand.replace(/_/g, ' ').toUpperCase()}
                  </div>
                </div>
              `;
            })
            .join("");
          
          document.getElementById("comparableLocationsList").innerHTML = listHtml || "<p>No comparable locations found.</p>";
        })
        .catch((error) => console.error("[MARKET_ANALYSIS] Error fetching data:", error));
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
          
          // Fetch builder information if location is available
          let bookedMessage = `Your cab has been booked with ${providerName}. Your booking reference is ${payload.cab_booking_reference}.`;
          if (lead.location) {
            fetch(`/builders/by-location/${encodeURIComponent(lead.location)}`)
              .then(res => res.json())
              .then(data => {
                if (data.builders && data.builders.length > 0) {
                  const builder = data.builders[0];
                  setCabStatus("Builder/Project", builder.name, "good");
                  setCabStatus("Project Location", builder.location, "good");
                  bookedMessage = `Your cab to ${builder.name} in ${lead.location} has been booked with ${providerName}. Reference: ${payload.cab_booking_reference}.`;
                  voiceLog.textContent = bookedMessage;
                  playBeep(760, 140);
                  speak(bookedMessage);
                }
              })
              .catch(err => {
                console.log("Builder info fetch error (non-critical):", err);
                voiceLog.textContent = bookedMessage;
                playBeep(760, 140);
                speak(bookedMessage);
              });
          } else {
            voiceLog.textContent = bookedMessage;
            playBeep(760, 140);
            speak(bookedMessage);
          }
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
      fetchAndRenderFunnelChart();
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

    async function getAnswerWithFallback(promptText, options = {}) {
      const { allowSkip = false, emptyValue = "" } = options;
      
      try {
        // First try voice input with retries
        return await waitForSpeech(promptText, { retries: 1, timeoutMs: 4000, allowSkip, emptyValue });
      } catch (voiceError) {
        // Voice input failed, show text fallback
        return new Promise((resolve) => {
          // Show fallback panel
          fallbackTextInputPanel.style.display = "block";
          fallbackQuestionText.textContent = promptText;
          fallbackTextInput.value = "";
          fallbackStatus.textContent = "";
          
          // Show/hide skip button based on allowSkip
          if (allowSkip) {
            fallbackSkipButton.style.display = "block";
          } else {
            fallbackSkipButton.style.display = "none";
          }
          
          // Log the fallback attempt
          voiceLog.textContent = "Voice input not captured. Please type your answer in the text box below.";
          fallbackStatus.textContent = "Waiting for text input...";
          
          // Focus on input
          fallbackTextInput.focus();
          
          // Handle submit
          const handleSubmit = () => {
            const answer = fallbackTextInput.value.trim();
            if (!answer && !allowSkip) {
              fallbackStatus.textContent = "Please enter an answer or click Skip if optional.";
              fallbackTextInput.focus();
              return;
            }
            
            // Clear event listeners
            fallbackSubmitButton.removeEventListener("click", handleSubmit);
            fallbackSkipButton.removeEventListener("click", handleSkip);
            fallbackTextInput.removeEventListener("keypress", handleKeyPress);
            
            // Hide fallback panel
            fallbackTextInputPanel.style.display = "none";
            
            // Log the captured answer
            if (answer) {
              voiceLog.textContent = `Captured: ${answer}`;
              fallbackStatus.textContent = "";
              resolve(answer);
            } else {
              voiceLog.textContent = "Skipped - marked as not required.";
              fallbackStatus.textContent = "";
              resolve(emptyValue);
            }
          };
          
          // Handle skip
          const handleSkip = () => {
            // Clear event listeners
            fallbackSubmitButton.removeEventListener("click", handleSubmit);
            fallbackSkipButton.removeEventListener("click", handleSkip);
            fallbackTextInput.removeEventListener("keypress", handleKeyPress);
            
            // Hide fallback panel
            fallbackTextInputPanel.style.display = "none";
            
            voiceLog.textContent = "Skipped - marked as not required.";
            fallbackStatus.textContent = "";
            resolve(emptyValue);
          };
          
          // Handle Enter key
          const handleKeyPress = (event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              handleSubmit();
            }
          };
          
          // Attach event listeners
          fallbackSubmitButton.addEventListener("click", handleSubmit);
          fallbackSkipButton.addEventListener("click", handleSkip);
          fallbackTextInput.addEventListener("keypress", handleKeyPress);
        });
      }
    }

    async function startVoiceIntake() {
      if (!recognitionSupported) {
        voiceLog.textContent = "Voice intake needs a browser with speech recognition support.";
        return;
      }
      if (recognitionBusy) {
        voiceLog.textContent = "Voice assistant is already listening. Please wait for the current input to complete.";
        return;
      }
      
      // Prevent multiple concurrent intakes
      if (window.voiceIntakeInProgress) {
        voiceLog.textContent = "Voice intake is already in progress. Please wait...";
        return;
      }
      window.voiceIntakeInProgress = true;

      try {
        stopSpeechPlayback();
        const name = await getAnswerWithFallback("Tell me the customer name.");
        document.getElementById("customerName").value = name;

        const employmentType = await getAnswerWithFallback("Is the customer salaried, in business, or self-employed?");
        document.getElementById("employmentType").value = parseEmploymentType(employmentType);

        const segmentAnswer = await getAnswerWithFallback("Is this a residential or commercial lead?");
        segmentSelect.value = parseSegment(segmentAnswer);
        syncSegmentFields();

        const location = await getAnswerWithFallback("What is the preferred location?");
        document.getElementById("location").value = inferLocation(location);

        const customerLocation = await getAnswerWithFallback(
          "What is the customer's current pickup location? You can say skip or not required.",
          { allowSkip: true, emptyValue: "" }
        );
        document.getElementById("customerLocation").value = heardSkipIntent(customerLocation) ? "" : inferLocation(customerLocation);

        const budget = await getAnswerWithFallback("What is the budget?");
        document.getElementById("budget").value = parseBudgetValue(budget);

        const timeline = await getAnswerWithFallback("What is the timeline in days?");
        document.getElementById("timelineDays").value = parseDaysValue(timeline);
        document.getElementById("profession").value = "";
        document.getElementById("totalExperienceYears").value = "";

        if (segmentSelect.value === "commercial") {
          const businessType = await getAnswerWithFallback("What type of business is this lead for?");
          document.getElementById("businessType").value = inferBusinessType(businessType);

          const sqftMin = await getAnswerWithFallback("What is the minimum square footage required?");
          document.getElementById("squareFeetMin").value = parseSquareFeetValue(sqftMin);

          const sqftMax = await getAnswerWithFallback("What is the maximum square footage required?");
          document.getElementById("squareFeetMax").value = parseSquareFeetValue(sqftMax);
        } else {
          const propertyType = await getAnswerWithFallback("What property type does the customer want?");
          document.getElementById("propertyType").value = inferResidentialPropertyType(propertyType);
        }

        const inquiry = await getAnswerWithFallback("Now describe the inquiry in one sentence.");
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
      } finally {
        window.voiceIntakeInProgress = false;
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
        const inquiry = await getAnswerWithFallback("Please describe the customer inquiry.");
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

    async function consumeStream(response) {
      startButton.disabled = true;
      submitManualButton.disabled = true;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          addEventRow(event);

          if (event.event === "lead_received") {
            leads.set(event.lead_id, {
              customer_name: event.payload.customer_name,
              inquiry: event.payload.inquiry,
              stage: "received",
              segment: event.payload.segment || document.getElementById("segment").value,
              location: document.getElementById("location").value,
              customer_location: document.getElementById("customerLocation").value
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
            
            // Fetch property details if recommendation exists
            if (event.payload.recommended_property_id) {
              fetch(`/properties/${event.payload.recommended_property_id}`)
                .then(res => res.json())
                .then(propData => {
                  lead.property_details = propData;
                  lead.recommended_property_id = event.payload.recommended_property_id;
                  
                  // Calculate distance from customer location if available
                  if (lead.customer_location && lead.location) {
                    // Mock distance calculation (in real scenario, use distance matrix)
                    const distanceMap = {
                      "Marathahalli-Whitefield": 8.2,
                      "Marathahalli-Sarjapur": 12.5,
                      "Marathahalli-Indiranagar": 6.3,
                      "Marathahalli-Koramangala": 7.1,
                      "Marathahalli-HSR Layout": 8.9,
                      "Marathahalli-MG Road": 9.2,
                      "Marathahalli-CBD Retail District": 10.1
                    };
                    const key = `${lead.customer_location}-${lead.location}`;
                    lead.distance_to_property = distanceMap[key] || 10;
                  }
                  
                  leads.set(event.lead_id, lead);
                  renderLeadCard(event.lead_id);
                })
                .catch(err => {
                  console.log("Property details fetch error:", err);
                  leads.set(event.lead_id, lead);
                  renderLeadCard(event.lead_id);
                });
            } else {
              leads.set(event.lead_id, lead);
              renderLeadCard(event.lead_id);
            }
          }

          if (event.event === "run_completed") {
            statusText.textContent = `Completed ${event.payload.processed_leads} simulated leads.`;
            fetchAndRenderFunnelChart();
          }
        }
      }

      startButton.disabled = false;
      submitManualButton.disabled = false;
      fetchAndRenderFunnelChart();
    }

    async function startStream() {
      resetBoards();
      statusText.textContent = "Streaming default CRM traffic...";
      const response = await fetch("/simulate/live/stream?delay_seconds=0.35");
      await consumeStream(response);
    }

    async function runManualLead() {
      resetBoards();
      statusText.textContent = "Streaming manual lead...";
      const response = await fetch("/simulate/live/stream?delay_seconds=0.35", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(manualPayload())
      });
      await consumeStream(response);
    }

    startButton.addEventListener("click", startStream);
    submitManualButton.addEventListener("click", runManualLead);
    loadDefaultButton.addEventListener("click", loadWhitefieldExample);
    loadCommercialButton.addEventListener("click", loadCommercialExample);
    segmentSelect.addEventListener("change", syncSegmentFields);
    startVoiceIntakeButton.addEventListener("click", startVoiceIntake);
    dictateInquiryButton.addEventListener("click", dictateInquiry);
    playLatestCallButton.addEventListener("click", playLatestCall);
    
    // Builder search functionality
    const searchBuildersButton = document.getElementById("searchBuildersButton");
    const builderSearchLocation = document.getElementById("builderSearchLocation");
    const builderSearchType = document.getElementById("builderSearchType");
    const builderSearchResults = document.getElementById("builderSearchResults");
    
    async function searchBuilders() {
      const location = builderSearchLocation.value;
      const type = builderSearchType.value;
      
      if (!location) {
        builderSearchResults.innerHTML = '<div class="builder-empty-state">Please select a location to search builders.</div>';
        return;
      }
      
      try {
        let url = `/builders/search?location=${encodeURIComponent(location)}`;
        if (type) {
          url += `&project_type=${encodeURIComponent(type)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.results_count === 0) {
          builderSearchResults.innerHTML = '<div class="builder-empty-state">No builders found for the selected criteria.</div>';
          return;
        }
        
        builderSearchResults.innerHTML = data.results.map(builder => `
          <div class="builder-card">
            <h3>${builder.name}</h3>
            <p>${builder.project_type}</p>
            <div class="builder-info-grid">
              <div class="builder-info-item">
                <div class="builder-info-label">Location</div>
                <div class="builder-info-value">${builder.location}</div>
              </div>
              <div class="builder-info-item">
                <div class="builder-info-label">Units</div>
                <div class="builder-info-value">${builder.units}</div>
              </div>
              <div class="builder-info-item" style="grid-column: 1 / -1;">
                <div class="builder-info-label">Coordinates</div>
                <div class="builder-info-value">${builder.coordinate}</div>
              </div>
            </div>
          </div>
        `).join('');
      } catch (error) {
        console.error("Builder search error:", error);
        builderSearchResults.innerHTML = '<div class="builder-empty-state">Error fetching builders. Please try again.</div>';
      }
    }
    
    if (searchBuildersButton) {
      searchBuildersButton.addEventListener("click", searchBuilders);
    }
    
    // Market analysis listeners - update on any form field change
    const marketAnalysisInputs = [
      document.getElementById("location"),
      document.getElementById("customerLocation"),
      document.getElementById("segment"),
      document.getElementById("budget")
    ];
    marketAnalysisInputs.forEach(input => {
      if (input) {
        input.addEventListener("change", fetchAndRenderMarketAnalysis);
        input.addEventListener("input", fetchAndRenderMarketAnalysis);
      }
    });
    
    if (!recognitionSupported && !playbackSupported) {
      voiceLog.textContent = "Voice features are unavailable in this browser. Use Chrome or Edge for speech recognition.";
    } else if (!recognitionSupported) {
      voiceLog.textContent = "Voice playback is available, but microphone dictation is not supported in this browser.";
    } else if (!playbackSupported) {
      voiceLog.textContent = "Voice dictation is available, but speech playback is not supported in this browser.";
    }
    loadWhitefieldExample();
    fetchAndRenderMarketAnalysis();
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