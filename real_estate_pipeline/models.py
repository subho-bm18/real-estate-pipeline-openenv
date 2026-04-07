from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LeaseTerms(BaseModel):
    lease_years: int | None = None
    monthly_rent: int | None = None
    deposit_months: int | None = None
    fit_out_support: bool | None = None


class CallTurn(BaseModel):
    speaker: Literal["agent", "customer"]
    text: str


class NotificationMessage(BaseModel):
    channel: Literal["chat", "sms", "whatsapp"]
    recipient: str
    message: str
    delivery_status: str = "sent"


class OpportunitySummary(BaseModel):
    opportunity_id: str
    segment: Literal["residential", "commercial"]
    title: str
    stage: str
    priority: str | None = None


class PropertyRecord(BaseModel):
    property_id: str
    segment: Literal["residential", "commercial"]
    title: str
    location: str
    price_type: Literal["sale", "rent", "lease"]
    price: int
    details: dict[str, Any] = Field(default_factory=dict)


class OpportunityDetail(BaseModel):
    opportunity_id: str
    segment: Literal["residential", "commercial"]
    customer_name: str
    inquiry: str
    profession: str | None = None
    total_experience_years: int | None = None
    employment_type: str | None = None
    preferred_cab_provider: str | None = None
    customer_location: str | None = None
    budget: int | None = None
    location: str | None = None
    timeline_days: int | None = None
    property_type: str | None = None
    business_type: str | None = None
    square_feet_min: int | None = None
    square_feet_max: int | None = None
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    stage: str = "new"
    category: str | None = None
    priority: str | None = None
    recommended_property_id: str | None = None
    lease_terms: LeaseTerms | None = None
    customer_contacted: bool = False
    interested_in_visit: bool | None = None
    cab_requested: bool | None = None
    builder_provides_cab: bool | None = None
    builder_cab_approved: bool | None = None
    pickup_eligible: bool | None = None
    drop_eligible: bool | None = None
    cab_eligibility_status: str | None = None
    cab_customer_response: str | None = None
    cab_booking_status: str | None = None
    cab_booking_provider: str | None = None
    cab_booking_reference: str | None = None
    cab_booking_mode: str | None = None
    cab_pickup_location: str | None = None
    cab_drop_location: str | None = None
    cab_handoff_url: str | None = None
    cab_booking_notes: str | None = None
    cab_booking_sla_seconds: int | None = None
    cab_booked_within_sla: bool | None = None
    cab_notifications: list[NotificationMessage] = Field(default_factory=list)
    last_contact_note: str | None = None
    call_outcome: str | None = None
    call_transcript: list[CallTurn] = Field(default_factory=list)
    appointment_type: str | None = None
    appointment_party: str | None = None
    
    # Site Visit & Proposal Phase
    site_visit_completed: bool = False
    site_visit_date: str | None = None
    site_visit_feedback: str | None = None  # "positive", "interested", "not_interested"
    site_visit_feedback_positive: bool = False
    
    proposal_sent: bool = False
    proposal_sent_date: str | None = None
    proposal_details: dict[str, Any] = Field(default_factory=dict)
    booking_amount_quoted: int | None = None
    
    # Follow-up Phase
    follow_up_count: int = 0
    follow_up_dates: list[str] = Field(default_factory=list)
    follow_up_responses: list[dict[str, Any]] = Field(default_factory=list)
    last_follow_up_date: str | None = None
    
    # Negotiation Phase
    negotiation_status: str | None = None  # "pending", "resolved", "failed"
    negotiation_round: int = 0
    negotiation_offers: list[dict[str, Any]] = Field(default_factory=list)
    customer_objections: list[str] = Field(default_factory=list)
    
    # Payment Phase
    booking_amount_paid: int = 0
    booking_payment_date: str | None = None
    booking_payment_method: str | None = None  # "bank_transfer", "check", "online"
    booking_payment_reference: str | None = None
    
    # Deal Finalization
    deal_finalized: bool = False
    deal_closed: bool = False
    deal_closed_date: str | None = None
    closing_value: int | None = None
    final_action_status: str | None = None  # "success", "abandoned", "pending"
    
    pending_objections: list[str] = Field(default_factory=list)
    landlord_counter_offer: LeaseTerms | None = None
    assigned_action: str | None = None


class Observation(BaseModel):
    task_id: str
    step_count: int
    remaining_steps: int
    queue: list[OpportunitySummary]
    active_opportunity: OpportunityDetail
    inventory_snapshot: list[PropertyRecord]
    business_rules: list[str]
    available_actions: list[str]
    last_action_error: str | None = None


class Reward(BaseModel):
    value: float
    components: dict[str, float] = Field(default_factory=dict)
    progress_signals: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


class Action(BaseModel):
    action_type: Literal[
        "classify_opportunity",
        "set_priority",
        "request_missing_info",
        "recommend_property",
        "call_customer",
        "confirm_site_visit_interest",
        "check_builder_cab_support",
        "respond_cab_eligibility",
        "book_cab",
        "schedule_visit",
        "schedule_builder_appointment",
        "schedule_landlord_meeting",
        "send_proposal",
        "customer_follow_up",
        "send_negotiation_offer",
        "send_payment_reminder",
        "process_booking_payment",
        "finalize_deal",
        "negotiate_terms",
        "resolve_objection",
        "accept_counter_offer",
        "send_commercial_proposal",
        "close_deal",
        "move_to_nurture",
        "recommend_lease_terms",
        "advance_stage",
        "drop_opportunity",
    ]
    opportunity_id: str
    category: str | None = None
    priority: str | None = None
    requested_fields: list[str] = Field(default_factory=list)
    property_id: str | None = None
    message: str | None = None
    visit_interest: bool | None = None
    cab_requested: bool | None = None
    cab_provider: str | None = None
    pickup_location: str | None = None
    drop_location: str | None = None
    appointment_party: str | None = None
    closing_value: int | None = None
    lease_terms: LeaseTerms | None = None
    objections_resolved: list[str] = Field(default_factory=list)
    stage: str | None = None
    reason: str | None = None
    
    # Proposal & Deal Closure Fields
    proposal_details: dict[str, Any] = Field(default_factory=dict)
    booking_amount_quoted: int | None = None
    follow_up_number: int | None = None  # Which follow-up round (1, 2, 3, etc.)
    customer_feedback: str | None = None  # Feedback from follow-up
    negotiation_offer: dict[str, Any] = Field(default_factory=dict)  # Modified offer details
    booking_amount_paid: int | None = None
    booking_payment_method: str | None = None
    booking_payment_reference: str | None = None


class StepResult(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: dict[str, Any] = Field(default_factory=dict)


class InboundLead(BaseModel):
    lead_id: str
    customer_name: str
    inquiry: str
    segment: Literal["residential", "commercial"] = "residential"
    profession: str | None = None
    total_experience_years: int | None = None
    employment_type: str | None = None
    preferred_cab_provider: str | None = None
    customer_location: str | None = None
    budget: int | None = None
    location: str | None = None
    timeline_days: int | None = None
    property_type: str | None = None
    business_type: str | None = None
    square_feet_min: int | None = None
    square_feet_max: int | None = None
    missing_fields: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    step: int
    thought: str
    action: Action
    reward: float
    done: bool
    grader_score: float
    last_action_error: str | None = None


class LeadSimulationResult(BaseModel):
    lead_id: str
    task_id: str
    success: bool
    final_score: float
    final_stage: str
    recommended_property_id: str | None = None
    assigned_action: str | None = None
    action_trace: list[AgentDecision] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)


class LiveTrafficSimulationRequest(BaseModel):
    leads: list[InboundLead] = Field(default_factory=list)


class LiveTrafficSimulationResponse(BaseModel):
    run_id: str
    processed_leads: int
    results: list[LeadSimulationResult] = Field(default_factory=list)
