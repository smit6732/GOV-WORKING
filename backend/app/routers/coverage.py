import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..config import settings

router = APIRouter(prefix="/coverage", tags=["coverage"])

# Metric CRS suitable for Gujarat (UTM zone 43N) so buffer/area math is in metres.
METRIC_SRID = 32643

DISTRICT_COVERAGE_SQL = text(
    """
    WITH region AS (
        SELECT ST_Buffer(ST_ConvexHull(ST_Collect(ST_Transform(geom, :metric_srid))), 1000) AS geom
        FROM police_stations WHERE district = :district
    ),
    covered_raw AS (
        SELECT ST_Union(ST_Buffer(ST_Transform(geom, :metric_srid), :radius)) AS geom
        FROM cameras WHERE district = :district
    ),
    covered AS (
        SELECT ST_Intersection(region.geom, COALESCE(covered_raw.geom, ST_GeomFromText('POLYGON EMPTY', :metric_srid))) AS geom
        FROM region, covered_raw
    ),
    gap AS (
        SELECT ST_Difference(region.geom, COALESCE(covered_raw.geom, ST_GeomFromText('POLYGON EMPTY', :metric_srid))) AS geom
        FROM region, covered_raw
    )
    SELECT
        ST_Area(region.geom) AS region_area,
        ST_Area(covered.geom) AS covered_area,
        ST_Area(gap.geom) AS gap_area,
        ST_AsGeoJSON(ST_Transform(gap.geom, 4326)) AS gap_geojson,
        ST_AsGeoJSON(ST_Transform(covered.geom, 4326)) AS covered_geojson
    FROM region, covered, gap
    """
)


def _compute_all_districts(db: Session, radius_m: int, district_filter: Optional[str] = None):
    districts_q = db.query(models.PoliceStation.district).distinct()
    if district_filter:
        districts_q = districts_q.filter(models.PoliceStation.district == district_filter)
    districts = sorted(r[0] for r in districts_q.all())

    from sqlalchemy import func

    count_rows = (
        db.query(models.Camera.district, func.count(models.Camera.id))
        .group_by(models.Camera.district)
        .all()
    )
    camera_counts = {d: c for d, c in count_rows}

    stats = []
    gap_features = []
    covered_features = []

    for district in districts:
        row = db.execute(
            DISTRICT_COVERAGE_SQL,
            {"district": district, "radius": radius_m, "metric_srid": METRIC_SRID},
        ).first()
        if row is None or row.region_area is None:
            continue

        region_km2 = (row.region_area or 0) / 1_000_000
        covered_km2 = (row.covered_area or 0) / 1_000_000
        gap_km2 = (row.gap_area or 0) / 1_000_000
        coverage_pct = round((covered_km2 / region_km2) * 100, 2) if region_km2 > 0 else 0.0

        stats.append(
            schemas.DistrictCoverageStat(
                district=district,
                camera_count=camera_counts.get(district, 0),
                region_area_km2=round(region_km2, 2),
                covered_area_km2=round(covered_km2, 2),
                gap_area_km2=round(gap_km2, 2),
                coverage_pct=coverage_pct,
            )
        )

        if row.gap_geojson:
            geom = json.loads(row.gap_geojson)
            if geom and geom.get("coordinates"):
                gap_features.append(
                    {"type": "Feature", "geometry": geom, "properties": {"district": district, "gap_area_km2": round(gap_km2, 2)}}
                )
        if row.covered_geojson:
            geom = json.loads(row.covered_geojson)
            if geom and geom.get("coordinates"):
                covered_features.append(
                    {"type": "Feature", "geometry": geom, "properties": {"district": district, "covered_area_km2": round(covered_km2, 2)}}
                )

    return stats, gap_features, covered_features


@router.get("/gap-analysis")
def gap_analysis(
    radius_m: int = Query(default=settings.default_coverage_radius_m, ge=50, le=5000),
    district: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stats, gap_features, covered_features = _compute_all_districts(db, radius_m, district)

    total_region = sum(s.region_area_km2 for s in stats)
    total_covered = sum(s.covered_area_km2 for s in stats)
    total_gap = sum(s.gap_area_km2 for s in stats)

    return {
        "radius_m": radius_m,
        "summary": {
            "total_region_km2": round(total_region, 2),
            "total_covered_km2": round(total_covered, 2),
            "total_gap_km2": round(total_gap, 2),
            "coverage_pct": round((total_covered / total_region) * 100, 2) if total_region > 0 else 0.0,
            "district_count": len(stats),
        },
        "districts": [s.model_dump() for s in stats],
        "gap_geojson": {"type": "FeatureCollection", "features": gap_features},
        "covered_geojson": {"type": "FeatureCollection", "features": covered_features},
    }


@router.get("/gap-analysis/export")
def gap_analysis_export(
    radius_m: int = Query(default=settings.default_coverage_radius_m, ge=50, le=5000),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    stats, _, _ = _compute_all_districts(db, radius_m)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["district", "camera_count", "region_area_km2", "covered_area_km2", "gap_area_km2", "coverage_pct"]
    )
    for s in stats:
        writer.writerow(
            [s.district, s.camera_count, s.region_area_km2, s.covered_area_km2, s.gap_area_km2, s.coverage_pct]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=coverage_gap_analysis.csv"},
    )
