// Model first, then a clearly labelled class illustration, then the universal default.
export function chooseArtwork(catalog, type, category, airline) {
  const porter = (airline === 'POE' || airline === 'PTR') && type && catalog['POE_' + type];
  const exact = porter || type && catalog[type];
  const grouped = catalog['class_' + category];
  const entry = exact || grouped || catalog.DEFAULT || {
    asset:'/media/default-aircraft.png', alt:'Representative aircraft illustration', label:'AIRCRAFT ILLUSTRATION'
  };
  return {...entry, accuracy:exact ? 'type' : grouped ? 'class' : 'default',
    caption:porter ? 'PORTER EDITION · ' + type : exact ? 'TYPE STUDY · ' + type : grouped ? 'CLASS STUDY · ' + (entry.label || 'AIRCRAFT') : 'AIRCRAFT ILLUSTRATION'};
}
