# Deal Closure Implementation Guide

## Overview

The real estate pipeline now supports a complete deal closure workflow from site visit through payment and deal finalization. This document explains the implementation details and how to use the system.

---

## 1. Architecture & Components

### Model Updates (models.py)

**New OpportunityDetail Fields:**
```python
# Site Visit Phase
site_visit_completed: bool
site_visit_date: str | None
site_visit_feedback: str | None
site_visit_feedback_positive: bool

# Proposal Phase
proposal_sent: bool
proposal_sent_date: str | None
proposal_details: dict[str, Any]
booking_amount_quoted: int | None

# Follow-up Phase
follow_up_count: int
follow_up_dates: list[str]
follow_up_responses: list[dict[str, Any]]
last_follow_up_date: str | None

# Negotiation Phase
negotiation_status: str | None
negotiation_round: int
negotiation_offers: list[dict[str, Any]]
customer_objections: list[str]

# Payment Phase
booking_amount_paid: int
booking_payment_date: str | None
booking_payment_method: str | None
booking_payment_reference: str | None

# Deal Finalization
deal_finalized: bool
deal_closed_date: str | None
final_action_status: str | None
```

**New Action Types:**
```python
"send_proposal"              # Send formal proposal with booking amount
"customer_follow_up"         # Check on prospect status and collect feedback
"send_negotiation_offer"     # Present modified offer during negotiation
"send_payment_reminder"      # Send booking amount payment details
"process_booking_payment"    # Record booking amount payment
"finalize_deal"              # Mark deal as closed after payment
```

---

## 2. Agent Decision Logic (LiveTrafficAgent)

The agent follows this decision tree for residential deals:

### Stage 1: Site Visit Booking & Completion
```
If segment == "residential":
  ├─ Has property recommendation? NO → Recommend property
  ├─ Customer interested in visit? NO → Move to nurture
  ├─ Has cab approval? NO → Check cab support
  ├─ Cab booked? NO → Book cab
  └─ Cab booked? YES → Advance to "site_visit_completed"
```

### Stage 2: Proposal Sending
```
If site_visit_completed AND NOT proposal_sent:
  ├─ Calculate booking amount (7.5% of property price)
  ├─ Prepare payment plan (7.5% + 20% + 72.5% milestones)
  ├─ Set possession timeline (24 months)
  ├─ List amenities and benefits
  └─ SEND PROPOSAL → proposal_sent = True
```

### Stage 3: Follow-up Cycle
```
If proposal_sent AND follow_up_count < 3:
  ├─ Check previous follow-up responses
  ├─ If positive response → Move to payment phase
  ├─ If objections noted → Move to negotiation
  ├─ If no response → Send follow-up
  │   └─ Increment follow_up_count
  └─ If follow_up_count >= 3 → Move to nurture
```

### Stage 4: Negotiation (If Needed)
```
If customer has objections AND negotiation_round < 3:
  ├─ Analyze objections (price, payment, amenities, etc.)
  ├─ Prepare counter-offer (e.g., 1.5L discount + extras)
  ├─ SEND NEGOTIATION OFFER
  ├─ If accepted → Move to payment
  ├─ If counter-objection → Increment negotiation_round
  └─ If negotiation_round >= 3 → Move to nurture
```

### Stage 5: Payment Reminder
```
If proposal accepted AND NOT booking_amount_paid:
  ├─ Calculate booking amount from proposal
  ├─ Prepare payment details
  │   ├─ Beneficiary account
  │   ├─ Reference number (Lead ID + Property ID)
  │   ├─ Payment deadline (72 hours)
  │   └─ Channels (bank transfer, check, online)
  └─ SEND PAYMENT REMINDER
```

### Stage 6: Deal Finalization
```
If booking_amount_paid > 0 AND NOT deal_finalized:
  ├─ Verify payment received
  ├─ Prepare booking agreement
  ├─ Schedule signing
  ├─ Set project manager/follow-up contact
  └─ FINALIZE DEAL → deal_closed = True
```

---

## 3. Action Handlers in Environment

Each action type needs a handler in the `env.py` file. Example handlers:

### send_proposal Handler
```python
if action.action_type == "send_proposal":
    opp = self.state()["active_opportunity"]
    opp["proposal_sent"] = True
    opp["proposal_sent_date"] = datetime.now(timezone.utc).isoformat()
    opp["proposal_details"] = action.proposal_details
    opp["booking_amount_quoted"] = action.booking_amount_quoted
    # Trigger notification: Send email/SMS/WhatsApp with proposal
    reward = 25.0  # Positive reward for sending proposal
```

### customer_follow_up Handler
```python
if action.action_type == "customer_follow_up":
    opp = self.state()["active_opportunity"]
    opp["follow_up_count"] += 1
    opp["last_follow_up_date"] = datetime.now(timezone.utc).isoformat()
    
    # Simulate customer response (in real system: actual customer input)
    # Possible responses: positive, objection, no_response
    response_status = simulate_customer_response(opp)
    
    opp["follow_up_responses"].append({
        "follow_up_number": opp["follow_up_count"],
        "date": datetime.now(timezone.utc).isoformat(),
        "status": response_status,  # "positive", "objection", "no_response"
        "feedback": "Customer message/response text"
    })
    
    reward = 15.0  # Positive for reaching out
```

### send_negotiation_offer Handler
```python
if action.action_type == "send_negotiation_offer":
    opp = self.state()["active_opportunity"]
    opp["negotiation_round"] += 1
    opp["customer_objections"] = action.customer_objections
    opp["negotiation_offers"].append({
        "round": opp["negotiation_round"],
        "offer": action.negotiation_offer,
        "date": datetime.now(timezone.utc).isoformat()
    })
    # Trigger notification: Send negotiation offer
    reward = 30.0  # Higher reward for engagement
```

### send_payment_reminder Handler
```python
if action.action_type == "send_payment_reminder":
    opp = self.state()["active_opportunity"]
    
    # Set payment details
    opp["payment_details"] = {
        "booking_amount": action.booking_amount_quoted,
        "due_date": (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(),
        "beneficiary": "Builder Escrow Account",
        "reference": f"{opp['opportunity_id']}_BOOKING"
    }
    
    # Trigger notification with payment link/details
    reward = 20.0
```

### process_booking_payment Handler
```python
if action.action_type == "process_booking_payment":
    opp = self.state()["active_opportunity"]
    opp["booking_amount_paid"] = action.booking_amount_paid
    opp["booking_payment_date"] = datetime.now(timezone.utc).isoformat()
    opp["booking_payment_method"] = action.booking_payment_method
    opp["booking_payment_reference"] = action.booking_payment_reference
    reward = 50.0  # Highest reward - payment received!
```

### finalize_deal Handler
```python
if action.action_type == "finalize_deal":
    opp = self.state()["active_opportunity"]
    opp["deal_finalized"] = True
    opp["deal_closed"] = True
    opp["deal_closed_date"] = datetime.now(timezone.utc).isoformat()
    opp["stage"] = "deal_closed"
    opp["final_action_status"] = "success"
    opp["closing_value"] = action.closing_value
    
    # Trigger final notification: Deal confirmed
    reward = 100.0  # Maximum reward - deal closed!
```

---

## 4. Test Leads & Scenarios

### Default Test Leads

**1. live_res_deal_001 - Quick Decision Buyer (Rohit Kumar)**
- Budget: ₹95 lakhs, 2BHK
- Timeline: 15 days (very short)
- Expected Flow: Proposal → Positive Response (1st follow-up) → Payment → Deal Closed
- Conversion Time: ~2 steps

**2. live_res_deal_002 - Hesitant Buyer (Kavya Desai)**
- Budget: ₹1.15 crore, 3BHK
- Timeline: 90 days (longer)
- Expected Flow: Proposal → No response → Follow-up 1 → No response → Follow-up 2 → Positive → Payment → Deal Closed
- Conversion Time: ~5 steps

**3. live_res_deal_003 - Negotiation Buyer (Vikram Iyer)**
- Budget: ₹92 lakhs (lower, will negotiate)
- Timeline: 60 days
- Expected Flow: Proposal → Objection (price too high) → Negotiation Offer 1 → Counter-objection → Negotiation Offer 2 → Acceptance → Payment → Deal Closed
- Conversion Time: ~6 steps

**4. live_res_deal_004 - Ready to Purchase (Sneha Reddy)**
- Budget: ₹1.2 crore (higher)
- Timeline: 20 days (very short)
- Expected Flow: Proposal → Positive Response (same day) → Payment → Deal Closed
- Conversion Time: ~2-3 steps

**5. live_res_deal_005 - Family Purchase (Anil Kapoor)**
- Budget: ₹98 lakhs
- Timeline: 45 days
- Notes: "Need to discuss with family"
- Expected Flow: Proposal → No response → Follow-up 1 → No response → Follow-up 2 → Acceptance → Payment → Deal Closed
- Conversion Time: ~5 steps

---

## 5. Event Streaming

The system streams events for dashboard visualization:

```json
{
  "event": "lead_step",
  "payload": {
    "action": "send_proposal",
    "booking_amount_quoted": 750000,
    "proposal_details": {...}
  }
}
```

```json
{
  "event": "lead_step",
  "payload": {
    "action": "customer_follow_up",
    "follow_up_number": 1,
    "customer_response": "positive"
  }
}
```

```json
{
  "event": "lead_step",
  "payload": {
    "action": "send_payment_reminder",
    "booking_amount": 750000,
    "payment_link": "..."
  }
}
```

```json
{
  "event": "lead_completed",
  "payload": {
    "final_stage": "deal_closed",
    "deal_closed": true,
    "booking_amount_paid": 750000,
    "closing_value": 9500000
  }
}
```

---

## 6. Dashboard Integration

### New Metrics to Display

**Deal Closure Funnel:**
```
Site Visits Completed → 8
Proposals Sent → 7
Follow-ups Completed → 6
Negotiations Resolved → 4
Payments Received → 3
Deals Closed → 3
```

**Payment Tracking:**
```
Total Booking Amount Quoted: ₹65 lakhs
Total Booking Amount Received: ₹35 lakhs
Payment Completion Rate: 53.8%
Average Payment Days: 3.2 days
```

**Stage Distribution:**
```
site_visit_completed: 8 leads
proposal_sent: 7 leads
follow_up_cycle: 4 leads
negotiation_phase: 2 leads
payment_phase: 2 leads
deal_closed: 3 leads
```

---

## 7. Configuration & Customization

### Adjustable Parameters

In the agent logic, you can customize:

```python
# Booking amount percentage
booking_amount = int((opportunity.budget or 0) * 0.075)  # Change to 0.10 for 10%

# Payment plan breakdown
{
    {"milestone": "Booking", "percentage": 7.5},
    {"milestone": "Agreement", "percentage": 20},
    {"milestone": "Construction", "percentage": 72.5},
}

# Max follow-ups
if opportunity.follow_up_count < 3:  # Change to 5 for more follow-ups

# Max negotiation rounds
if opportunity.negotiation_round < 3:  # Change to 4 for more flexibility

# Discount in negotiation offer
"price_adjustment": -150000,  # Adjust builder's flexibility

# Possession timeline
"possession_months": 24,  # Adjust as needed
```

---

## 8. Integration with CRM

### Database Schema (Recommended)

```sql
-- Proposals table
CREATE TABLE proposals (
  id SERIAL PRIMARY KEY,
  lead_id VARCHAR(50),
  booking_amount INT,
  sent_date TIMESTAMP,
  status ENUM('sent', 'viewed', 'accepted', 'rejected'),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Follow-ups table
CREATE TABLE followups (
  id SERIAL PRIMARY KEY,
  lead_id VARCHAR(50),
  follow_up_number INT,
  sent_date TIMESTAMP,
  response_status VARCHAR(50),
  customer_feedback TEXT,
  created_at TIMESTAMP
);

-- Negotiations table
CREATE TABLE negotiations (
  id SERIAL PRIMARY KEY,
  lead_id VARCHAR(50),
  round_number INT,
  offer JSON,
  response VARCHAR(50),
  created_at TIMESTAMP
);

-- Payments table
CREATE TABLE payments (
  id SERIAL PRIMARY KEY,
  lead_id VARCHAR(50),
  booking_amount INT,
  paid_amount INT,
  payment_date TIMESTAMP,
  payment_method VARCHAR(50),
  reference_id VARCHAR(100),
  status ENUM('pending', 'received', 'reconciled'),
  created_at TIMESTAMP
);
```

---

## 9. Workflow Examples

### Example 1: Quick Deal Closure
```
Day 5, 6:00 PM | send_proposal (₹95L, booking ₹7.125L)
Day 6, 5:00 PM | customer_follow_up → Response: "POSITIVE"
Day 6, 6:00 PM | send_payment_reminder (₹7.125L due by Day 6)
Day 6, 11:00 PM | process_booking_payment (₹7.125L received)
Day 7, 10:00 AM | finalize_deal → ✅ CLOSED
```

### Example 2: Negotiation-Heavy Deal
```
Day 5, 6:00 PM | send_proposal (₹95L asked, ₹7.125L booking)
Day 6, 5:00 PM | customer_follow_up → Response: "OBJECTION - Too high"
Day 6, 6:00 PM | send_negotiation_offer (₹93.5L + 1.5L discount, extra parking)
Day 7, 4:00 PM | customer_follow_up → Response: "OBJECTION - More discount needed"
Day 7, 6:00 PM | send_negotiation_offer (₹92L + 2L discount, extended warranty)  
Day 8, 2:00 PM | customer_follow_up → Response: "POSITIVE - Accepted"
Day 8, 6:00 PM | send_payment_reminder (₹7.125L due by Day 9)
Day 9, 10:00 AM | process_booking_payment (₹7.125L received)
Day 9, 2:00 PM | finalize_deal → ✅ CLOSED
```

### Example 3: Lost to Nurture
```
Day 5, 6:00 PM | send_proposal (₹95L, booking ₹7.125L)
Day 6, 5:00 PM | customer_follow_up (1/3) → No Response
Day 9, 4:00 PM | customer_follow_up (2/3) → No Response
Day 14, 3:00 PM | customer_follow_up (3/3) → No Response
Day 14, 6:00 PM | move_to_nurture → ⏸ PAUSED (retry in 14 days)
```

---

## 10. Future Enhancements

### Phase 2 Features
- SMS/WhatsApp integration for proposals and reminders
- Payment gateway integration for online booking amount collection
- Document management (agreements, specifications, guarantees)
- Possession timeline tracking and updates
- Customer feedback loop for improvements

### Phase 3 Features
- Multi-unit booking (family members, investor groups)
- Referral program integration
- After-sales service tracking (warranty, maintenance)
- Repeat customer identification
- Analytics dashboards for sales team performance

---

## 11. Troubleshooting

### Issue: Leads stuck in proposal stage
**Solution:** Check if site_visit_completed flag is being set properly by the environment

### Issue: Negotiation not triggering
**Solution:** Ensure customer_objections are being captured in follow-up responses

### Issue: Payment not recorded
**Solution:** Verify process_booking_payment is being triggered after customer confirms payment

### Issue: Leads not moving to finalization
**Solution:** Check that booking_amount_paid > 0 is the condition for finalization

