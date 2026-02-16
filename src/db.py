import os
import motor.motor_asyncio
from datetime import datetime

class Database:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.client = motor.motor_asyncio.AsyncIOMotorClient(self.uri)
        self.db = self.client.interview  # Database name
        self.collection = self.db.sessions    # Collection name

    async def save_session_document(self, session_data: dict):
        """
        Saves the complete interview session to MongoDB.
        """
        # Add a tailored timestamp if not present
        if "created_at" not in session_data:
            session_data["created_at"] = datetime.utcnow()
        
        result = await self.collection.insert_one(session_data)
        return str(result.inserted_id)

# Global instance
db_instance = Database()

async def get_db():
    return db_instance
