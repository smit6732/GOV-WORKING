import React from 'react'
import { MapContainer, TileLayer, LayersControl } from 'react-leaflet'

export const GUJARAT_CENTER = [22.6, 71.6]

/** Shared base map (tile layers + Gujarat center) — used by GISMap and by
 * Model 2's Vehicle Search route view, so there's exactly one map setup to
 * maintain instead of two copies drifting apart. */
export default function MapBase({ zoom = 7, height = '70vh', children }) {
  return (
    <MapContainer center={GUJARAT_CENTER} zoom={zoom} style={{ height }}>
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Streets">
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite">
          <TileLayer
            attribution="Tiles &copy; Esri"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      {children}
    </MapContainer>
  )
}
