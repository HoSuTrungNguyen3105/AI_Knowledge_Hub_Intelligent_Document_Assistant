// MongoDB indexes for the AI Agent Factory (database: ai_factory).
// The Code Execution Service creates these automatically on first connect,
// so running this file is OPTIONAL — it exists for inspection and for
// setups that point MONGO_URL at an externally managed MongoDB.
//
// Run with:  mongosh "mongodb://localhost:27017/ai_factory" db/mongo-indexes.js

db.projects.createIndex({ id: 1 }, { unique: true });
db.agent_runs.createIndex({ project_id: 1, created_at: 1 });
db.tasks.createIndex({ project_id: 1 });
db.qa_reviews.createIndex({ project_id: 1 });
db.artifacts.createIndex({ project_id: 1 });
