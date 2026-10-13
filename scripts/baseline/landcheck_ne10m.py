import json, shapefile, math
from shapely.geometry import shape, Point, LineString, box
from shapely.ops import unary_union
from shapely.prepared import prep
import sys
v=json.load(open('vessels.json'))
sf=shapefile.Reader('land/ne_10m_land')
region=box(5,52,32,70)
polys=[shape(s.__geo_interface__).intersection(region) for s in sf.shapes()]
land=unary_union([p for p in polys if not p.is_empty]); pl=prep(land)
pred=[x for x in v if x['predicted_latitude'] is not None]
print('vessels',len(v),'with projection',len(pred))
end_land=seg_land=start_land=0; seg_len=[]
bad=[]
for x in pred:
    a=Point(x['current_longitude'],x['current_latitude']); b=Point(x['predicted_longitude'],x['predicted_latitude'])
    s=LineString([a,b])
    sl=pl.contains(a); el=pl.contains(b); cr=pl.intersects(s)
    start_land+=sl; end_land+=el; seg_land+=cr
    if cr: bad.append((x['vessel_id'],round(x['sog'],1),x['cog'],x['heading'],x['nav_stat'],sl,el))
print('start on land (coarse map):',start_land)
print('endpoint on land:',end_land, f'{100*end_land/len(pred):.1f}%')
print('path touches land:',seg_land, f'{100*seg_land/len(pred):.1f}%')
# only those that start in water
w=[x for x in pred if not pl.contains(Point(x['current_longitude'],x['current_latitude']))]
cw=sum(1 for x in w if pl.intersects(LineString([(x['current_longitude'],x['current_latitude']),(x['predicted_longitude'],x['predicted_latitude'])])))
print('started in water:',len(w),' path crosses land:',cw, f'{100*cw/max(1,len(w)):.1f}%')
# heading vs cog disagreement
d=[]
for x in pred:
    h=x['heading']; c=x['cog']
    if h is not None and h<360:
        diff=abs((h-c+180)%360-180); d.append(diff)
print('heading known:',len(d),' |heading-cog|>30deg:',sum(1 for q in d if q>30))
sog=[x['sog'] for x in pred]
print('sog distribution of projected: <2kn',sum(1 for s in sog if s<2),' 2-5',sum(1 for s in sog if 2<=s<5),' >=5',sum(1 for s in sog if s>=5))
print('sample bad:',bad[:12])
# all vessels: stale / stationary shares
import datetime as dt
now=dt.datetime.fromisoformat('2026-10-13T10:30:17+00:00')
ages=[(now-dt.datetime.fromisoformat(x['current_timestamp'].replace('Z','+00:00'))).total_seconds() for x in v]
ages.sort(); n=len(ages)
print('age s: median',ages[n//2],'p90',ages[int(n*.9)],'max',ages[-1])
print('sog None',sum(1 for x in v if x['sog'] is None),'cog None',sum(1 for x in v if x['cog'] is None),'sog>=102',sum(1 for x in v if x['sog'] is not None and x['sog']>=102))
print('vessel_type known:',sum(1 for x in v if x['vessel_type']!='Unknown'))
