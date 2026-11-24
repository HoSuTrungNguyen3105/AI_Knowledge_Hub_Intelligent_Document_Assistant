// MongoDB indexes for the AI Agent Factory (database: MONGODB_DATABASE).
// The Code Execution Service creates these automatically on first connect,
// so running this file is OPTIONAL — it exists for inspection and for
// setups that use an externally managed MongoDB (e.g. Atlas).
//
// Run with:  mongosh "<your MONGODB_URI>" db/mongo-indexes.js

db.projects.createIndex({ id: 1 }, { unique: true });
db.agent_runs.createIndex({ project_id: 1, created_at: 1 });
db.tasks.createIndex({ project_id: 1 });
db.qa_reviews.createIndex({ project_id: 1 });
db.artifacts.createIndex({ project_id: 1 });
