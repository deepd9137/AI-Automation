You are a senior AI SaaS architect and full-stack engineer.

Build a production-ready MVP for an AI-powered Customer Engagement & Lead Conversion Assistant for coaches, consultants, and small businesses.

# PRODUCT GOAL

The platform should:
- answer FAQs using company documents
- automate customer support
- qualify leads intelligently
- schedule appointments
- support multi-platform communication
- automate follow-ups
- provide admin analytics/dashboard

The system should be scalable and designed as a future SaaS product.

--------------------------------------------------
# CORE FEATURES
--------------------------------------------------

## 1. AI FAQ ASSISTANT (RAG)

Users can upload:
- PDFs
- DOCX
- TXT
- FAQs
- website text

The system should:
- chunk documents
- create embeddings
- store vectors
- retrieve relevant context
- answer user queries using an LLM

Requirements:
- conversation memory
- citation/source support
- fallback response if confidence is low

Use:
- LangChain or LlamaIndex
- OpenAI embeddings
- vector database

--------------------------------------------------
## 2. LEAD QUALIFICATION SYSTEM

The AI assistant should:
- ask structured follow-up questions
- capture:
  - name
  - phone
  - email
  - budget
  - urgency
  - service interest

Generate:
- lead score
- hot/warm/cold categorization

Store leads in database.

Admin should be able to:
- view leads
- update lead status
- export leads

--------------------------------------------------
## 3. APPOINTMENT BOOKING

Integrate:
- Google Calendar
- Calendly API

Capabilities:
- fetch available slots
- book meetings automatically
- send confirmation emails
- timezone support

--------------------------------------------------
## 4. MULTI-CHANNEL SUPPORT

Support:
- Website chatbot
- WhatsApp integration
- Instagram DM architecture support
- Telegram integration

Architecture should allow future channel additions.

--------------------------------------------------
## 5. FOLLOW-UP AUTOMATION

If lead becomes inactive:
- trigger automated follow-up

Examples:
- reminder after 24h
- discount message
- appointment reminder
- feedback request

Implement:
- scheduled jobs
- retry handling
- event-based workflow triggers

--------------------------------------------------
## 6. ADMIN DASHBOARD

Dashboard should show:
- total conversations
- active leads
- booked appointments
- chatbot usage
- conversion rate
- lead pipeline

Admin capabilities:
- upload documents
- manage prompts
- manage FAQs
- view chat history
- configure AI behavior

--------------------------------------------------
# TECH STACK
--------------------------------------------------

Frontend:
- Next.js
- TypeScript
- TailwindCSS
- ShadCN UI

Backend:
- FastAPI
- Python

AI Layer:
- OpenAI API
- LangChain
- RAG pipeline

Database:
- PostgreSQL

Vector Database:
- ChromaDB initially
- architecture should support Pinecone later

Authentication:
- JWT/Auth system

Deployment:
- Vercel (frontend)
- Railway/Render (backend)

--------------------------------------------------
# ARCHITECTURE REQUIREMENTS
--------------------------------------------------

Implement clean modular architecture:

backend/
├── api/
├── services/
├── agents/
├── rag/
├── database/
├── models/
├── routes/
├── auth/
├── scheduler/
├── integrations/
├── utils/

frontend/
├── app/
├── components/
├── dashboard/
├── chat-widget/
├── hooks/
├── services/

--------------------------------------------------
# REQUIRED SYSTEM FLOW
--------------------------------------------------

1. User sends message
2. API receives request
3. Conversation manager checks context
4. RAG retrieves relevant documents
5. LLM generates answer
6. Lead extraction system analyzes intent
7. If high-intent:
   - collect lead info
   - suggest appointment
8. Store conversation + lead data
9. Trigger follow-up workflows if needed

--------------------------------------------------
# DATABASE TABLES
--------------------------------------------------

Design schemas for:
- users
- businesses
- documents
- embeddings metadata
- conversations
- messages
- leads
- appointments
- automation logs

--------------------------------------------------
# AI BEHAVIOR REQUIREMENTS
--------------------------------------------------

The assistant should:
- sound professional
- ask concise questions
- avoid hallucinations
- escalate to human if uncertain
- personalize responses
- maintain conversational memory

--------------------------------------------------
# UI REQUIREMENTS
--------------------------------------------------

Frontend should include:
- responsive admin dashboard
- floating chat widget
- analytics cards
- lead management table
- document upload page
- settings page
- appointment calendar view

Design:
- modern SaaS UI
- minimal
- clean spacing
- smooth animations

--------------------------------------------------
# SECURITY REQUIREMENTS
--------------------------------------------------

Implement:
- API validation
- rate limiting
- authentication middleware
- encrypted secrets
- secure file uploads
- RBAC-ready architecture

--------------------------------------------------
# SCALABILITY REQUIREMENTS
--------------------------------------------------

Architecture must support:
- multi-tenant SaaS
- multiple businesses
- separate knowledge bases
- large document uploads
- future agent workflows

--------------------------------------------------
# BONUS FEATURES (IF POSSIBLE)
--------------------------------------------------

- voice AI support
- multilingual support
- sentiment analysis
- CRM integrations
- Stripe subscription billing
- analytics AI insights
- agent handoff to humans

--------------------------------------------------
# OUTPUT REQUIREMENTS
--------------------------------------------------

Generate:
1. full project architecture
2. backend code
3. frontend code
4. API routes
5. database schema
6. RAG pipeline
7. Docker setup
8. deployment instructions
9. environment variables template
10. production-ready folder structure

Code should be:
- clean
- modular
- scalable
- documented
- production-oriented

Use best engineering practices throughout.