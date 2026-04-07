# Real Estate Deal Closure Process Flow
## From Site Visit to Payment & Deal Finalization

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESIDENTIAL DEAL CLOSURE PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────────┘

STAGE 1: SITE VISIT COMPLETED
├─ Description: Customer has visited property with builder/agent
├─ Prerequisites: builder_appointment_scheduled = True
├─ Triggers: Site visit day confirmed, customer feedback collected
└─ Outcome: site_visit_completed = True

STAGE 2: PROPOSAL PREPARATION & SENDING
├─ Description: Builder prepares and sends formal proposal to customer
├─ Prerequisites: site_visit_completed = True, site_visit_feedback_positive = True
├─ Builder Actions:
│  ├─ Calculate final offer price (with discounts if applicable)
│  ├─ Prepare payment plan (booking amount, installments)
│  ├─ Prepare possession schedule
│  ├─ Include legal documents (title check, builder credentials)
│  └─ Send via email, SMS, WhatsApp
├─ Agent Actions:
│  ├─ Action: "send_proposal"
│  ├─ Payload: proposal_details, booking_amount_quoted, payment_plan
│  └─ Timestamp: proposal_sent_date
└─ Outcome: proposal_sent = True

STAGE 3: CUSTOMER FOLLOW-UP CYCLE
├─ Description: Series of follow-ups to understand customer decision
├─ Timing: 
│  ├─ Follow-up 1: 24-48 hours after proposal
│  ├─ Follow-up 2: 3-5 days after proposal
│  ├─ Follow-up 3: 7-10 days after proposal
├─ Agent Actions Per Follow-up:
│  ├─ Action: "customer_follow_up"
│  ├─ Message: "Have you reviewed the proposal? Any questions?"
│  ├─ Collect: Customer feedback, concerns, objections
│  ├─ Response Paths:
│  │  ├─ Positive: Move to Stage 5 (Payment Reminder)
│  │  ├─ Objections: Move to Stage 4 (Negotiation)
│  │  └─ No Response: Try next follow-up
│  └─ Increment: follow_up_count += 1
└─ Outcome: Customer decides → next stage triggers

STAGE 4: NEGOTIATION (If Needed)
├─ Description: Negotiate price, payment terms, or other conditions
├─ Triggers When: Customer has objections or concerns
├─ Negotiation Points:
│  ├─ Price adjustment / builder discount
│  ├─ Payment plan modification (booking amount, milestone-based)
│  ├─ Possession date adjustment
│  ├─ Additional inclusions (parking, maintenance)
│  └─ Legal terms (warranty, construction quality, cancellation)
├─ Agent Actions:
│  ├─ Action: "send_negotiation_offer"
│  ├─ Iterate: Present offers, collect counter-offers
│  ├─ Round Limit: Max 3-4 negotiation rounds
│  └─ Outcome: Agreement reached or negotiation_failed
├─ Success Paths:
│  ├─ Agreement: Move to Stage 5
│  └─ Impasse: Move to Nurture (cool-off period, retry later)
└─ Outcome: negotiation_status = "resolved" or "pending"

STAGE 5: PAYMENT REMINDER & BOOKING AMOUNT
├─ Description: Send booking amount payment details to customer
├─ Prerequisites: Proposal accepted or negotiation resolved
├─ Payment Details:
│  ├─ Booking Amount: 5-10% of property price (e.g., ₹50-100 lakhs)
│  ├─ Payment Deadline: Usually 48-72 hours
│  ├─ Payment Methods: Bank transfer, check, online payment
│  ├─ Beneficiary: Builder's escrow account
│  └─ Reference: Lead ID + Property ID for tracking
├─ Agent Actions:
│  ├─ Action: "send_payment_reminder"
│  ├─ Channels: Email, SMS, WhatsApp with payment link
│  ├─ Include: Invoice, bank details, payment instructions
│  ├─ Follow-up: If not paid in 48hrs, send reminder
│  └─ Escalation: If not paid in 72hrs, contact customer directly
├─ Payment Tracking:
│  ├─ booking_amount_quoted: Amount due
│  ├─ booking_amount_paid: Amount received
│  └─ booking_payment_date: When payment received
└─ Outcome: Payment received and confirmed

STAGE 6: DEAL FINALIZATION
├─ Description: Final agreement signed, deal confirmed
├─ Prerequisites: Booking amount paid, all terms agreed
├─ Finalization Steps:
│  ├─ Verify payment received in builder's account
│  ├─ Send deal confirmation document
│  ├─ Schedule signing of booking agreement
│  ├─ Send possession timeline
│  ├─ Assign project manager / follow-up contact
│  └─ Archive all communications and documents
├─ Agent Actions:
│  ├─ Action: "finalize_deal"
│  ├─ Set: deal_finalized = True
│  ├─ Set: deal_closed = True
│  ├─ Timestamp: deal_closed_date
│  └─ Send: Congratulations message with next steps
├─ Records Updated:
│  ├─ stage = "deal_closed"
│  ├─ closing_value = full_property_price
│  ├─ deal_finalized = True
│  └─ final_action_status = "success"
└─ Outcome: ✅ DEAL CLOSED - Revenue recognized


┌─────────────────────────────────────────────────────────────────────────────┐
│                   DECISION TREE & BRANCHING LOGIC                            │
└─────────────────────────────────────────────────────────────────────────────┘

Site Visit Completed?
├─ No → Stay in "builder_appointment_scheduled" stage
└─ Yes (with positive feedback)
   └─ Send Proposal
      └─ Proposal Sent Successfully?
         ├─ No → Retry or contact customer manually
         └─ Yes
            └─ Follow-up Cycle (Round 1)
               ├─ Positive Response → Send Payment Reminder
               ├─ Objections → Negotiation Phase
               │  └─ Resolved? 
               │     ├─ Yes → Send Payment Reminder
               │     └─ No → Move to Nurture
               └─ No Response → Follow-up Cycle (Round 2+)
                  └─ Max Follow-ups Reached?
                     ├─ Yes → Move to Nurture
                     └─ No → Schedule next follow-up


┌─────────────────────────────────────────────────────────────────────────────┐
│                        DATA MODEL ENHANCEMENTS                               │
└─────────────────────────────────────────────────────────────────────────────┘

New OpportunityDetail Fields:
├─ site_visit_date: datetime | None
├─ site_visit_feedback: str | None  ("positive", "interested", "not_interested")
├─ site_visit_feedback_positive: bool = False
├─ site_visit_completed: bool = False
│
├─ proposal_sent: bool = False (existing, repurposed)
├─ proposal_sent_date: datetime | None
├─ proposal_details: dict[str, Any] = {} (price, terms, payment plan)
├─ booking_amount_quoted: int | None (5-10% of property price)
│
├─ follow_up_count: int = 0
├─ follow_up_dates: list[datetime] = []
├─ follow_up_responses: list[dict] = []  (customer feedback per follow-up)
├─ last_follow_up_date: datetime | None
│
├─ negotiation_status: str | None  ("pending", "resolved", "failed")
├─ negotiation_round: int = 0 (existing)
├─ negotiation_offers: list[dict] = []  (offer history)
├─ customer_objections: list[str] = []  (negotiation points)
│
├─ booking_amount_paid: int = 0
├─ booking_payment_date: datetime | None
├─ booking_payment_method: str | None  ("bank_transfer", "check", "online")
├─ booking_payment_reference: str | None
│
├─ deal_finalized: bool = False
├─ deal_closed_date: datetime | None
└─ final_action_status: str  ("success", "abandoned", "pending")


New Action Types:
├─ "send_proposal" → Send formatted proposal with all terms
├─ "customer_follow_up" → Check on proposal status, collect feedback
├─ "send_negotiation_offer" → Send modified offer during negotiation
├─ "send_payment_reminder" → Send booking amount payment details
├─ "process_booking_payment" → Record payment received
└─ "finalize_deal" → Mark deal as closed and prepare for next phase


┌─────────────────────────────────────────────────────────────────────────────┐
│                      TIMELINES & SLAs                                        │
└─────────────────────────────────────────────────────────────────────────────┘

Phase                    | SLA             | Action Points
─────────────────────────┼─────────────────┼──────────────────────────────────
Proposal Sending         | <= 24 hours     | After positive site visit feedback
Follow-up 1              | 24-48 hours     | After proposal sent
Follow-up 2              | 3-5 days        | If no response to Follow-up 1
Follow-up 3              | 7-10 days       | If no response to Follow-up 2
Payment Deadline         | 48-72 hours     | After customer commitment
Payment Reminder 1       | 24 hours        | After sending payment details
Payment Reminder 2       | 48 hours        | If payment not received
Escalation               | 72 hours        | Escalate to builder/manager

Deal Finalization        | <= 7 days       | After payment received
Complete Closure         | <= 10 days      | After finalization
```

## Example Lead Journey

```
Lead: Priya Sharma (2BHK, Budget: ₹1Cr, Indiranagar)
─────────────────────────────────────────────────────────

Day 1    | 10:00 AM  | Lead receives builder appointment → Site visit scheduled
Day 5    | 2:00 PM   | Site visit completed → Feedback: "Very interested, but price high"
Day 5    | 6:00 PM   | send_proposal: Proposal sent (₹1.02 Cr, 10% = ₹10.2L booking)
Day 6    | 5:00 PM   | customer_follow_up: "Have you reviewed?" → Response: "Need to discuss"
Day 7    | 10:00 AM  | send_negotiation_offer: "Builder offers ₹99.5L with 5% discount"
Day 7    | 3:00 PM   | Negotiation feedback: "Acceptable, interested to proceed"
Day 7    | 6:00 PM   | send_payment_reminder: "Booking amount ₹10L due by Day 9"
Day 8    | 2:00 PM   | Payment received: "₹10L transferred to escrow"
Day 8    | 4:00 PM   | finalize_deal: Deal confirmed, booking agreement sent
Day 9    | 10:00 AM  | ✅ DEAL CLOSED - Revenue ₹99.5 Cr, Booking ₹10L received
```

## Implementation Strategy

1. **Model Updates**: Add new fields to OpportunityDetail in models.py
2. **Action Types**: Extend Action.action_type with new actions
3. **Agent Logic**: Update LiveTrafficAgent.choose_action() with new decision paths
4. **Event Streaming**: Stream new events for proposal, follow-ups, negotiations, payments
5. **Test Cases**: Add leads demonstrating complete flow through all stages
6. **Dashboard**: Display proposal status, follow-up counts, negotiation rounds, payment status

