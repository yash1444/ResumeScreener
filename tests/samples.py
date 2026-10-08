"""Synthetic resumes used by the tests."""

STRONG = """Asha Rao
asha.rao@example.com | github.com/asharao-dev

Summary
Backend engineer building agentic systems.

Skills
Python, FastAPI, PostgreSQL, Redis, LangGraph, Docker, GCP

Projects
Stateful Research Agent | Python, LangGraph, FastAPI, ChromaDB
• Built a multi-agent research workflow with LangGraph: planner, retriever and critic agents with tool calling and shared state.
• Implemented RAG over 10k documents using embeddings and ChromaDB, with an evaluation pipeline measuring hallucination rate.
• Added Redis caching, async FastAPI endpoints, retries with fallback on LLM failure, and pytest unit tests. Deployed with Docker on Cloud Run (GCP).

Experience
Backend Intern, Acme
• Developed asyncio services on PostgreSQL and Redis; reduced p95 latency by 40%.
"""

JS_ONLY = """Ravi Kumar
ravi@example.com

Skills
JavaScript, React, Next.js, Node.js, Java, Spring Boot

Projects
Shop Frontend | React, Next.js
• Built an e-commerce storefront with React and Redux.
Experience
Frontend Intern
• Developed REST integrations with Node.js and Express.
"""

PYTHON_NO_AI = """Meera Iyer
meera@example.com

Skills
Python, Django, PostgreSQL, Redis, Docker

Projects
Inventory API | Python, Django, PostgreSQL
• Designed a REST API with Django and PostgreSQL, with unit tests and Redis caching.
Experience
Backend Intern
• Built Celery workers and optimised SQL queries.
"""

SKILLS_ONLY_AI = """Dev Patel
dev@example.com

Skills
Python, FastAPI, LangChain, RAG, LLMs, OpenAI

Projects
Library Management System | Python, Flask, MySQL
• Developed a CRUD application for managing books and members using Flask and MySQL.
"""

THIN_WRAPPER = """Tara Singh
tara@example.com

Skills
Python, Streamlit

Projects
Chatbot using OpenAI API | Python, Streamlit
• Built a chatbot that sends the user's question to the OpenAI API and shows the answer in Streamlit.
"""

JS_LANGCHAIN_ONLY = """Omar Ali
omar@example.com

Skills
JavaScript, TypeScript, LangChain.js, OpenAI

Projects
Docs Assistant | TypeScript, LangChain
• Built a RAG assistant over docs using LangChain.js, OpenAI embeddings and Pinecone.
"""

PYTHON_IN_SKILLS_ONLY = """Lena Fischer
lena@example.com

Skills
Python, Java, Spring Boot

Projects
Doc Assistant | Java, Spring AI, OpenAI, pgvector
• Built a RAG assistant with embeddings, pgvector retrieval and OpenAI tool calling for internal documents.
• Implemented an evaluation pipeline measuring answer accuracy and added Redis caching.
Experience
Backend Intern
• Developed Spring Boot services with PostgreSQL.
"""
