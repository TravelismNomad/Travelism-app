from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from supabase import create_client

app = FastAPI(title="Travelism API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


class ProfileData(BaseModel):
    telegram_id: int
    first_name: Optional[str] = None
    phone: Optional[str] = None
    citizenship: Optional[str] = None
    departure_city: Optional[str] = None
    language: Optional[str] = "ru"


class TripData(BaseModel):
    telegram_id: int
    destination_city: str
    destination_country: str
    destination_emoji: Optional[str] = "🌍"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    adults: int = 1
    children: int = 0
    budget: Optional[float] = None
    flight_url: Optional[str] = None
    hotel_url: Optional[str] = None
    plan_summary: Optional[str] = None


@app.get("/")
def root():
    return {"status": "Travelism API is running", "version": "1.0"}


@app.post("/api/profile")
def create_or_update_profile(data: ProfileData):
    existing = supabase.table("users")\
        .select("*")\
        .eq("telegram_id", data.telegram_id)\
        .execute()

    profile_dict = data.dict(exclude_none=True)
    profile_dict["updated_at"] = "NOW()"

    if existing.data:
        result = supabase.table("users")\
            .update(profile_dict)\
            .eq("telegram_id", data.telegram_id)\
            .execute()
    else:
        profile_dict["points"] = 30  # Бонус за регистрацию
        result = supabase.table("users")\
            .insert(profile_dict)\
            .execute()

    return {"success": True, "data": result.data}


@app.get("/api/profile/{telegram_id}")
def get_profile(telegram_id: int):
    result = supabase.table("users")\
        .select("*")\
        .eq("telegram_id", telegram_id)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    return result.data[0]


@app.post("/api/trips")
def save_trip(data: TripData):
    result = supabase.table("trips")\
        .insert(data.dict())\
        .execute()

    # Начислить баллы
    supabase.table("users")\
        .update({"points": supabase.table("users").select("points").eq("telegram_id", data.telegram_id).execute().data[0]["points"] + 10})\
        .eq("telegram_id", data.telegram_id)\
        .execute()

    return {"success": True, "trip_id": result.data[0]["id"] if result.data else None}


@app.get("/api/trips/{telegram_id}")
def get_trips(telegram_id: int, limit: int = 10):
    result = supabase.table("trips")\
        .select("*")\
        .eq("telegram_id", telegram_id)\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()

    return {"trips": result.data, "count": len(result.data)}


@app.get("/api/places")
def get_places(city: Optional[str] = None, category: Optional[str] = None,
               halal: Optional[bool] = None, limit: int = 20):
    query = supabase.table("places").select("*").eq("status", "approved")

    if city:
        query = query.ilike("city", f"%{city}%")
    if category:
        query = query.eq("category", category)
    if halal:
        query = query.eq("halal_friendly", True)

    result = query.limit(limit).execute()
    return {"places": result.data}


@app.post("/api/places")
def add_place(place: dict):
    place["status"] = "pending"
    result = supabase.table("places").insert(place).execute()
    return {"success": True, "message": "Заявка принята на модерацию"}


@app.post("/api/reviews")
def add_review(review: dict):
    result = supabase.table("reviews").insert(review).execute()

    # Обновить рейтинг места
    reviews = supabase.table("reviews")\
        .select("rating")\
        .eq("place_id", review["place_id"])\
        .execute()

    if reviews.data:
        avg = sum(r["rating"] for r in reviews.data) / len(reviews.data)
        supabase.table("places")\
            .update({"rating_avg": round(avg, 1), "reviews_count": len(reviews.data)})\
            .eq("id", review["place_id"])\
            .execute()

    return {"success": True}


@app.post("/api/points")
def add_points(telegram_id: int, points: int, reason: str = ""):
    existing = supabase.table("users")\
        .select("points, level")\
        .eq("telegram_id", telegram_id)\
        .execute()

    if not existing.data:
        return {"error": "User not found"}

    current = existing.data[0]["points"]
    new_points = current + points

    # Обновить уровень
    level = 1
    if new_points >= 500: level = 2
    if new_points >= 1500: level = 3
    if new_points >= 3000: level = 4
    if new_points >= 5000: level = 5
    if new_points >= 15000: level = 6

    supabase.table("users")\
        .update({"points": new_points, "level": level})\
        .eq("telegram_id", telegram_id)\
        .execute()

    return {"points": new_points, "level": level, "added": points}
