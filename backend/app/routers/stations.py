from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get("/geojson")
def stations_geojson(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    stations = db.query(models.PoliceStation).all()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s.longitude, s.latitude]},
            "properties": {
                "id": s.id,
                "district": s.district,
                "station_name": s.station_name,
                "address": s.address,
            },
        }
        for s in stations
    ]
    return {"type": "FeatureCollection", "features": features}
