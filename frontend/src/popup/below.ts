/**
 * A Leaflet popup that hangs below its point, tip pointing up. Leaflet pins a
 * popup's bottom edge to the point, so a popup that changes height (switching
 * tabs, opening a list) moves its header and tabs; pinning the top edge keeps
 * them still and lets only the bottom edge move.
 *
 * Overrides two private Leaflet 1.9 methods (_updatePosition, _adjustPan) —
 * re-check them when upgrading Leaflet (below.test.ts fails if they vanish).
 */
import L from 'leaflet';

// Private Leaflet state the overrides read and write.
interface PopupInternals {
  _map: L.Map & { _panAnim?: { stop(): void } };
  _latlng: L.LatLng;
  _container: HTMLElement;
  _containerWidth: number;
  _containerLeft: number;
  _containerTop: number;
  _zoomAnimated: boolean;
  _autopanning: boolean;
  _getAnchor(): L.Point;
}

export const BelowPopup = L.Popup.extend({
  options: { offset: [0, 0], className: 'tc-popup-below' },

  _updatePosition(this: PopupInternals & L.Popup) {
    if (!this._map) return;
    const pos = this._map.latLngToLayerPoint(this._latlng);
    let offset = L.point(this.options.offset as L.PointExpression);
    const anchor = this._getAnchor();
    if (this._zoomAnimated) L.DomUtil.setPosition(this._container, pos.add(anchor));
    else offset = offset.add(pos).add(anchor);
    this._containerTop = offset.y;
    this._containerLeft = -Math.round(this._containerWidth / 2) + offset.x;
    this._container.style.top = `${this._containerTop}px`;
    this._container.style.bottom = '';
    this._container.style.left = `${this._containerLeft}px`;
  },

  /** Leaflet's own auto-pan, measured from the popup's top edge instead of its bottom. */
  _adjustPan(this: PopupInternals & L.Popup) {
    if (!this.options.autoPan) return;
    const map = this._map;
    map._panAnim?.stop();
    if (this._autopanning) { this._autopanning = false; return; }
    const marginTop = parseInt(L.DomUtil.getStyle(this._container, 'marginTop') ?? '', 10) || 0;
    const height = this._container.offsetHeight + marginTop;
    const width = this._containerWidth;
    const layerPos = L.point(this._containerLeft, this._containerTop).add(L.DomUtil.getPosition(this._container));
    const pos = map.layerPointToContainerPoint(layerPos);
    const padding = L.point(this.options.autoPanPadding ?? [5, 5]);
    const tl = L.point(this.options.autoPanPaddingTopLeft ?? padding);
    const br = L.point(this.options.autoPanPaddingBottomRight ?? padding);
    const size = map.getSize();
    let dx = 0;
    let dy = 0;
    if (pos.x + width + br.x > size.x) dx = pos.x + width - size.x + br.x;
    if (pos.x - dx - tl.x < 0) dx = pos.x - tl.x;
    if (pos.y + height + br.y > size.y) dy = pos.y + height - size.y + br.y;
    if (pos.y - dy - tl.y < 0) dy = pos.y - tl.y;
    if (dx || dy) {
      if (this.options.keepInView) this._autopanning = true;
      map.fire('autopanstart').panBy([dx, dy]);
    }
  },
});

export function belowPopup(options?: L.PopupOptions): L.Popup {
  return new (BelowPopup as unknown as new (o?: L.PopupOptions) => L.Popup)(options);
}
