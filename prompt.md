# ROLE

You are a principal software architect, senior AI engineer, SaaS product architect, DevOps engineer, and technical project manager.

Your task is to generate a COMPLETE production-grade `SPECIFICATION.md` document for an AI SaaS product.

The document must be EXTREMELY detailed, actionable, and structured so that:
- a solo founder
- junior developers
- AI coding agents
- future contributors

can build the project systematically without confusion.

The specification should function as:
- product requirement document (PRD)
- software architecture document
- engineering handbook
- execution roadmap
- DevOps guide
- development workflow standard
- quality assurance guide

The output must be PROFESSIONAL and STARTUP-GRADE.

--------------------------------------------------
# PROJECT NAME
--------------------------------------------------

AI Customer Engagement & Lead Conversion Assistant

--------------------------------------------------
# PROJECT OVERVIEW
--------------------------------------------------

This platform is an AI-powered assistant for:
- coaches
- consultants
- local businesses
- agencies
- clinics
- service providers

The assistant should:
- answer customer FAQs
- automate support
- qualify leads
- schedule appointments
- automate follow-ups
- integrate with multiple communication channels
- provide analytics/dashboard
- scale into a SaaS platform

--------------------------------------------------
# IMPORTANT OUTPUT REQUIREMENT
--------------------------------------------------

Generate a COMPLETE `SPECIFICATION.md` file.

The file must be:
- structured
- sectioned properly
- production-grade
- startup-level quality
- implementation-oriented

DO NOT generate vague summaries.

Generate REAL engineering specifications.

--------------------------------------------------
# REQUIRED SECTIONS
--------------------------------------------------

# 1. Executive Summary
Explain:
- what the product is
- who it serves
- why it matters
- market opportunity
- key business value

--------------------------------------------------

# 2. Problem Statement

Clearly explain:
- operational pain points
- lead conversion issues
- delayed responses
- support inefficiencies
- customer drop-offs
- cost of human support
- business automation gap

Include:
- target user pain points
- business impact
- scalability problems

--------------------------------------------------

# 3. Solution Overview

Describe:
- AI assistant capabilities
- lead automation
- multi-channel communication
- AI workflows
- RAG-based FAQ system
- scheduling system
- analytics

--------------------------------------------------

# 4. Product Goals

Include:
- business goals
- technical goals
- scalability goals
- SaaS goals
- automation goals
- passive income potential
- reliability goals

--------------------------------------------------

# 5. Non-Goals

Explicitly define:
- features intentionally excluded from MVP
- limitations
- future roadmap items not included initially

--------------------------------------------------

# 6. User Personas

Create detailed personas:
- coach
- consultant
- local business owner
- admin/operator
- customer/end-user

For each:
- goals
- frustrations
- workflows
- technical ability

--------------------------------------------------

# 7. Functional Requirements

Provide exhaustive feature requirements for:
- chatbot
- RAG pipeline
- lead management
- authentication
- appointment scheduling
- notifications
- follow-ups
- analytics
- admin dashboard
- multi-tenant support
- integrations
- vector search
- file uploads
- prompt management
- memory/context handling

Each requirement should include:
- description
- inputs
- outputs
- validation rules
- edge cases
- failure handling

--------------------------------------------------

# 8. Non-Functional Requirements

Define:
- performance requirements
- uptime targets
- response time limits
- scalability expectations
- rate limiting
- security standards
- maintainability
- observability
- accessibility
- cost optimization
- logging
- monitoring
- API standards

--------------------------------------------------

# 9. Complete System Architecture

Generate FULL architecture explanation.

Include:
- frontend architecture
- backend architecture
- AI orchestration layer
- RAG pipeline
- vector database
- database layer
- authentication layer
- scheduler/workflow engine
- integrations layer
- deployment architecture

Provide:
- component responsibilities
- data flow
- service boundaries
- scaling considerations
- fault tolerance

Also generate:
- Mermaid diagrams
- architecture flowcharts
- request lifecycle diagrams
- database relation diagrams

--------------------------------------------------

# 10. Tech Stack Decision Document

For EVERY technology:
- explain WHY it was selected
- alternatives considered
- tradeoffs
- future scalability implications

Include:
- frontend
- backend
- database
- vector database
- authentication
- hosting
- CI/CD
- monitoring
- AI orchestration
- queue systems
- caching
- storage

--------------------------------------------------

# 11. Folder Structure

Generate COMPLETE production-grade folder structure for:
- frontend
- backend
- infrastructure
- scripts
- tests
- docker
- github workflows

Explain purpose of each directory.

--------------------------------------------------

# 12. Database Design

Generate:
- ER diagrams
- schema definitions
- relationships
- indexing strategy
- multi-tenant isolation strategy
- soft delete strategy
- audit logging strategy

Include tables:
- users
- organizations
- conversations
- messages
- leads
- appointments
- automation logs
- uploaded documents
- embeddings metadata
- integrations
- billing
- notifications

--------------------------------------------------

# 13. API Design

Generate:
- REST API specs
- endpoint naming conventions
- request/response examples
- authentication strategy
- error handling standards
- pagination standards
- versioning strategy

Include:
- Swagger/OpenAPI standards

--------------------------------------------------

# 14. AI/RAG Architecture

Generate exhaustive RAG system specs:
- chunking strategy
- embedding generation
- retrieval strategy
- reranking
- prompt engineering
- memory handling
- hallucination prevention
- context window optimization
- semantic search
- metadata filtering

Include:
- failure handling
- retry strategy
- token optimization
- latency optimization
- future agent architecture

--------------------------------------------------

# 15. Frontend Architecture

Define:
- component hierarchy
- routing
- state management
- data fetching
- auth handling
- dashboard layout
- responsive behavior
- loading/error states

Include:
- UI/UX standards
- design system
- reusable component strategy

--------------------------------------------------

# 16. Backend Engineering Standards

STRICTLY define:
- coding conventions
- naming conventions
- service-layer architecture
- dependency injection
- DTO usage
- schema validation
- exception handling
- logging standards
- testing requirements

The document must enforce:
- clean architecture
- SOLID principles
- modularity
- production-grade patterns

--------------------------------------------------

# 17. Strict Code Quality Rules

Create HARD RULES:
- no business logic inside routes
- no duplicate code
- typed responses only
- environment variables validation
- centralized configs
- no hardcoded secrets
- strict linting
- strict formatting
- mandatory tests

Include:
- PR review checklist
- code review standards
- definition of clean code

--------------------------------------------------

# 18. Security Specifications

Define:
- JWT strategy
- RBAC architecture
- API protection
- rate limiting
- secure file uploads
- secret management
- SQL injection prevention
- XSS prevention
- CSRF handling
- prompt injection prevention
- tenant isolation

--------------------------------------------------

# 19. DevOps & Deployment

Generate:
- Docker strategy
- docker-compose
- staging/prod environments
- CI/CD workflows
- GitHub Actions
- environment separation
- automated deployments
- rollback strategy
- monitoring stack
- logging stack

Include:
- backup strategy
- disaster recovery
- migration strategy

--------------------------------------------------

# 20. Git Workflow

MANDATORY:
Define automated Git workflow.

Requirements:
- separate branch per phase
- auto commit after milestone completion
- auto push workflow
- PR template
- issue templates
- semantic commit messages

Define:
- branch naming strategy
- release tagging
- hotfix strategy

Example:
main
develop
feature/phase-1-auth
feature/phase-2-rag
feature/phase-3-chatbot

--------------------------------------------------

# 21. Automation Requirements

IMPORTANT:
The specification must include AUTOMATION-FIRST development.

Include systems that:
- automatically run tests
- automatically lint code
- automatically format code
- automatically detect errors
- automatically generate API docs
- automatically update changelog
- automatically push commits
- automatically validate environment variables
- automatically run migrations
- automatically detect vulnerabilities

Include:
- pre-commit hooks
- husky
- lint-staged
- CI validation
- automated health checks

--------------------------------------------------

# 22. Development Phases

Generate DETAILED phased roadmap.

Each phase must include:
- objectives
- deliverables
- dependencies
- estimated duration
- success criteria
- validation checklist
- risks
- rollback strategy

Example phases:
1. Project setup
2. Auth system
3. Database layer
4. AI integration
5. RAG system
6. Chat system
7. Lead management
8. Scheduling
9. Dashboard
10. Integrations
11. Production hardening
12. SaaS readiness

--------------------------------------------------

# 23. Definition of Done (VERY IMPORTANT)

For EACH phase define:
- code quality requirements
- test coverage requirements
- documentation requirements
- deployment validation
- security validation
- performance validation
- logging validation
- rollback readiness

Define:
- what counts as COMPLETE
- what is NOT acceptable

--------------------------------------------------

# 24. Beginner-Friendly Execution Guide

Create EXTREMELY CLEAR guidance for:
- what to do BEFORE starting
- what to do DURING each phase
- what to do AFTER completing a phase
- how to validate work
- how to debug issues
- how to recover from failures

Include:
- command sequences
- environment setup
- local development workflow
- debugging methodology
- testing workflow

--------------------------------------------------

# 25. Debugging & Failure Recovery

Create a dedicated section for:
- debugging methodology
- common backend issues
- frontend issues
- database issues
- Docker issues
- AI/RAG issues
- deployment failures

Include:
- logging strategy
- tracing
- observability
- reproducible debugging process

--------------------------------------------------

# 26. Testing Strategy

Define:
- unit tests
- integration tests
- e2e tests
- load testing
- API testing
- AI response testing
- hallucination testing
- security testing

Specify:
- tools
- frameworks
- minimum coverage

--------------------------------------------------

# 27. Monitoring & Analytics

Define:
- application monitoring
- AI usage tracking
- token usage monitoring
- latency tracking
- business analytics
- conversion analytics
- alerting strategy

--------------------------------------------------

# 28. Cost Optimization Strategy

Include:
- minimizing token usage
- caching
- batching
- model selection strategy
- infra cost optimization
- vector DB optimization

--------------------------------------------------

# 29. SaaS Scalability Plan

Explain:
- tenant isolation
- subscription architecture
- billing readiness
- scaling strategy
- horizontal scaling
- queue systems
- async processing

--------------------------------------------------

# 30. Future Roadmap

Include future features:
- voice agents
- multilingual AI
- CRM integrations
- analytics AI
- autonomous workflows
- AI agents
- mobile apps

--------------------------------------------------

# 31. Final Engineering Principles

Define STRICT engineering philosophy:
- simplicity first
- scalability second
- modularity always
- automation first
- security by default
- documentation mandatory
- no shortcuts
- production-ready mindset

--------------------------------------------------
# OUTPUT STYLE
--------------------------------------------------

The generated SPECIFICATION.md must:
- use markdown
- use proper headings
- use tables
- use diagrams
- use code blocks
- use Mermaid diagrams
- be extremely structured
- be implementation-oriented
- be beginner friendly but professional
- contain real engineering detail

--------------------------------------------------
# IMPORTANT ENGINEERING REQUIREMENTS
--------------------------------------------------

The specification MUST enforce:
- clean architecture
- modular code
- scalable systems
- strict typing
- production-ready patterns
- reusable components
- reusable services
- centralized configuration
- observability
- automation-first workflow

--------------------------------------------------
# IMPORTANT AUTOMATION REQUIREMENTS
--------------------------------------------------

The specification must strongly encourage:
- reducing repetitive manual work
- scripting repetitive tasks
- auto-generating documentation
- auto-generating changelogs
- auto-commits after milestones
- CI/CD automation
- AI-assisted debugging workflows
- automated testing before merges

--------------------------------------------------
# FINAL OUTPUT
--------------------------------------------------

Generate ONE COMPLETE `SPECIFICATION.md` file only.

The output should feel like:
- a real startup engineering handbook
- a senior architect design document
- a deployable execution roadmap
- a production SaaS blueprint

The document should be comprehensive enough that development can begin immediately with minimal ambiguity.