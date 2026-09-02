const list = document.querySelector("#measurement-list");
const template = document.querySelector("#measurement-template");
const search = document.querySelector("#search");
const environmentFilter = document.querySelector("#environment-filter");
const sort = document.querySelector("#sort");
let measurements = [];

const titleCase = value => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
const level = value => value == null ? "—" : `${Number(value).toFixed(1)} dB`;
const duration = seconds => {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours ? `${hours}:${String(minutes).padStart(2,"0")}:${String(remainder).padStart(2,"0")}` : `${minutes}:${String(remainder).padStart(2,"0")}`;
};
const locationLabel = location => [location.city, location.country].filter(Boolean).join(", ") || "Location withheld";
const attributionLabel = attribution => {
  if (attribution.mode === "anonymous") return "Anonymous";
  return [attribution.name, attribution.organisation].filter(Boolean).join(" · ") || "Attributed contributor";
};
const newestFirst = (a,b) => b.completedAt.localeCompare(a.completedAt);
const levelForSort = (item,key) => {
  const value = item.levels[key];
  if (value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const highestLevelFirst = key => (a,b) => {
  const aLevel = levelForSort(a,key);
  const bLevel = levelForSort(b,key);
  if (aLevel == null) return bLevel == null ? newestFirst(a,b) : 1;
  if (bLevel == null) return -1;
  return bLevel-aLevel || newestFirst(a,b);
};
const sortComparators = {
  newest:newestFirst,
  oldest:(a,b) => a.completedAt.localeCompare(b.completedAt),
  loudest:highestLevelFirst("laeq"),
  lafmax:highestLevelFirst("lafmax"),
  lcpeak:highestLevelFirst("lcpeak")
};

function detailsRow(term, description) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = description;
  wrapper.append(dt, dd);
  return wrapper;
}

function renderCard(item) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector("article");
  fragment.querySelector("h3").textContent = item.title;
  fragment.querySelector(".environment-pill").textContent = titleCase(item.environmentType);
  const time = fragment.querySelector("time");
  time.dateTime = item.completedAt;
  time.textContent = new Intl.DateTimeFormat(undefined,{day:"numeric",month:"short",year:"numeric"}).format(new Date(item.completedAt));
  fragment.querySelector(".location").textContent = locationLabel(item.location);
  fragment.querySelector(".laeq").textContent = level(item.levels.laeq);
  fragment.querySelector(".lafmax").textContent = level(item.levels.lafmax);
  fragment.querySelector(".lcpeak").textContent = level(item.levels.lcpeak);
  fragment.querySelector(".duration").textContent = duration(item.durationSeconds);
  fragment.querySelector(".measurement-id").textContent = item.id;
  const recordLink = fragment.querySelector(".record-link");
  recordLink.href = item.recordUrl;
  recordLink.setAttribute("aria-label", `Open public record for ${item.title}`);
  const details = fragment.querySelector(".details-list");
  details.append(
    detailsRow("Environment", `${titleCase(item.environmentGroup)} · ${titleCase(item.environmentType)}`),
    detailsRow("LAFmin", level(item.levels.lafmin)),
    detailsRow("LCeq", level(item.levels.lceq)),
    detailsRow("LZeq", level(item.levels.lzeq)),
    detailsRow("Calibration", titleCase(item.calibration.method)),
    detailsRow("Quality", titleCase(item.quality)),
    detailsRow("Contributor", attributionLabel(item.attribution)),
    detailsRow("Licence", item.license.replaceAll("-", " "))
  );
  if (item.notes) {
    const notes = fragment.querySelector(".notes");
    notes.hidden = false;
    notes.textContent = item.notes;
  }
  if (item.photo) {
    const wrap = fragment.querySelector(".photo-wrap");
    const image = fragment.querySelector(".measurement-photo");
    wrap.hidden = false;
    image.src = item.photo;
    image.alt = `Public photograph for ${item.title}`;
  }
  card.dataset.search = [item.title,item.id,item.environmentGroup,item.environmentType,locationLabel(item.location)].join(" ").toLowerCase();
  return fragment;
}

function render() {
  const query = search.value.trim().toLowerCase();
  const environment = environmentFilter.value;
  const order = sort.value;
  const filtered = measurements.filter(item => (!query || item._search.includes(query)) && (!environment || item.environmentGroup === environment));
  filtered.sort(sortComparators[order] || newestFirst);
  list.replaceChildren(...filtered.map(renderCard));
  document.querySelector("#result-count").textContent = `${filtered.length} ${filtered.length === 1 ? "result" : "results"}`;
  document.querySelector("#empty-state").hidden = filtered.length !== 0;
}

fetch("data/measurements.json")
  .then(response => { if (!response.ok) throw new Error(response.status); return response.json(); })
  .then(data => {
    measurements = data.measurements.map(item => ({...item,_search:[item.title,item.id,item.environmentGroup,item.environmentType,locationLabel(item.location)].join(" ").toLowerCase()}));
    const groups = [...new Set(measurements.map(item => item.environmentGroup))].sort();
    for (const group of groups) environmentFilter.add(new Option(titleCase(group), group));
    document.querySelector("#measurement-count").textContent = measurements.length;
    document.querySelector("#location-count").textContent = measurements.filter(item => item.location.city || item.location.country).length;
    list.setAttribute("aria-busy", "false");
    render();
  })
  .catch(() => {
    list.setAttribute("aria-busy", "false");
    document.querySelector("#error-state").hidden = false;
  });

[search,environmentFilter,sort].forEach(control => control.addEventListener("input", render));
