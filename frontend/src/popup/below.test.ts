// @vitest-environment jsdom
import L from 'leaflet';
import { describe, expect, it } from 'vitest';
import { BelowPopup, belowPopup } from './below';

function mapAt(): L.Map {
  document.body.innerHTML = '<div id="m" style="width:400px;height:400px"></div>';
  return L.map('m', { zoomAnimation: false }).setView([49.28, -123.12], 15);
}

describe('belowPopup', () => {
  it('still overrides the private Leaflet methods it relies on', () => {
    const proto = L.Popup.prototype as unknown as Record<string, unknown>;
    expect(typeof proto._updatePosition).toBe('function');
    expect(typeof proto._adjustPan).toBe('function');
    const own = BelowPopup.prototype as unknown as Record<string, unknown>;
    expect(own._updatePosition).not.toBe(proto._updatePosition);
    expect(own._adjustPan).not.toBe(proto._adjustPan);
  });

  it('pins the popup by its top edge, at the point', () => {
    const map = mapAt();
    const popup = belowPopup({ autoPan: false }).setLatLng([49.28, -123.12]).setContent('<p>hi</p>').openOn(map);
    const el = popup.getElement()!;
    expect(el.classList.contains('tc-popup-below')).toBe(true);
    expect(el.style.top).not.toBe('');
    expect(el.style.bottom).toBe('');
    const anchor = map.latLngToLayerPoint([49.28, -123.12]);
    const top = L.DomUtil.getPosition(el).y + parseFloat(el.style.top);
    expect(top).toBe(anchor.y);
  });

  it('takes content from a function, as bindPopup does', () => {
    const map = mapAt();
    const marker = L.circleMarker([49.28, -123.12]).addTo(map);
    marker.bindPopup(belowPopup({ autoPan: false }).setContent(() => '<p>lazy</p>'));
    marker.openPopup();
    expect(marker.getPopup()!.getElement()!.textContent).toContain('lazy');
  });
});
