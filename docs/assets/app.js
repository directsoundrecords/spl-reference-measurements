const list = document.querySelector("#measurement-list");
const template = document.querySelector("#measurement-template");
const search = document.querySelector("#search");
const environmentFilter = document.querySelector("#environment-filter");
const sort = document.querySelector("#sort");
const measurementCount = document.querySelector("#measurement-count");
const locationCount = document.querySelector("#location-count");
const resultCount = document.querySelector("#result-count");
const emptyState = document.querySelector("#empty-state");
const errorState = document.querySelector("#error-state");
const controls = [search,environmentFilter,sort];
let measurements = [];

const titleCase = value => {
  const text = String(value ?? "").trim();
  return text ? text.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase()) : "—";
};
const finiteNumber = value => {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const level = value => {
  const number = finiteNumber(value);
  return number == null ? "—" : `${number.toFixed(1)} dB`;
};
const duration = seconds => {
  const number = finiteNumber(seconds);
  if (number == null) return "—";
  const total = Math.max(0, Math.round(number));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours ? `${hours}:${String(minutes).padStart(2,"0")}:${String(remainder).padStart(2,"0")}` : `${minutes}:${String(remainder).padStart(2,"0")}`;
};
const locationLabel = location => [location?.city, location?.country].filter(Boolean).join(", ") || "Location withheld";
const attributionLabel = attribution => {
  if (attribution?.mode === "anonymous") return "Anonymous";
  return [attribution?.name, attribution?.organisation].filter(Boolean).join(" · ") || "Attributed contributor";
};
const dateText = value => String(value ?? "");
const dateValue = value => {
  const milliseconds = Date.parse(dateText(value));
  return Number.isFinite(milliseconds) ? milliseconds : null;
};
const dateLabel = value => {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : new Intl.DateTimeFormat(undefined,{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(date);
};
const idFirst = (a,b) => String(a.id ?? "").localeCompare(String(b.id ?? ""));
const dateFirst = direction => (a,b) => {
  const aDate = dateValue(a.completedAt);
  const bDate = dateValue(b.completedAt);
  if (aDate == null) return bDate == null ? idFirst(a,b) : 1;
  if (bDate == null) return -1;
  return direction * (aDate-bDate) || idFirst(a,b);
};
const newestFirst = dateFirst(-1);
const oldestFirst = dateFirst(1);
const levelForSort = (item,key) => finiteNumber(item.levels?.[key]);
const highestLevelFirst = key => (a,b) => {
  const aLevel = levelForSort(a,key);
  const bLevel = levelForSort(b,key);
  if (aLevel == null) return bLevel == null ? newestFirst(a,b) : 1;
  if (bLevel == null) return -1;
  return bLevel-aLevel || newestFirst(a,b);
};
const sortComparators = {
  newest:newestFirst,
  oldest:oldestFirst,
  loudest:highestLevelFirst("laeq"),
  lafmax:highestLevelFirst("lafmax"),
  lcpeak:highestLevelFirst("lcpeak")
};
const resultLabel = count => `${count} ${count === 1 ? "result" : "results"}`;
const searchText = item => [item.title,item.id,item.environmentGroup,item.environmentType,locationLabel(item.location)].filter(Boolean).join(" ").toLowerCase();

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
  time.dateTime = dateText(item.completedAt);
  time.textContent = dateLabel(item.completedAt);
  fragment.querySelector(".location").textContent = locationLabel(item.location);
  fragment.querySelector(".laeq").textContent = level(item.levels?.laeq);
  fragment.querySelector(".lafmax").textContent = level(item.levels?.lafmax);
  fragment.querySelector(".lcpeak").textContent = level(item.levels?.lcpeak);
  fragment.querySelector(".duration").textContent = duration(item.durationSeconds);
  fragment.querySelector(".measurement-id").textContent = String(item.id ?? "");
  const recordLink = fragment.querySelector(".record-link");
  recordLink.href = String(item.recordUrl ?? "#");
  recordLink.setAttribute("aria-label", `Open public record for ${item.title ?? "this measurement"}`);
  const details = fragment.querySelector(".details-list");
  details.append(
    detailsRow("Environment", `${titleCase(item.environmentGroup)} · ${titleCase(item.environmentType)}`),
    detailsRow("LAFmin", level(item.levels?.lafmin)),
    detailsRow("LCeq", level(item.levels?.lceq)),
    detailsRow("LZeq", level(item.levels?.lzeq)),
    detailsRow("Calibration", titleCase(item.calibration?.method || item.calibration?.status)),
    detailsRow("Quality", titleCase(item.quality)),
    detailsRow("Contributor", attributionLabel(item.attribution)),
    detailsRow("Licence", String(item.license ?? "—").replaceAll("-", " "))
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
    image.alt = `Public photograph for ${item.title ?? "this measurement"}`;
  }
  card.dataset.search = searchText(item);
  return fragment;
}

function render() {
  const query = search.value.trim().toLowerCase();
  const environment = environmentFilter.value;
  const order = sort.value;
  const filtered = measurements.filter(item => (!query || item._search.includes(query)) && (!environment || item.environmentGroup === environment));
  filtered.sort(sortComparators[order] || newestFirst);
  const cards = filtered.map(renderCard);
  list.replaceChildren(...cards);
  resultCount.textContent = resultLabel(filtered.length);
  const filtersAreActive = Boolean(query || environment);
  const catalogueIsEmpty = measurements.length === 0;
  emptyState.textContent = catalogueIsEmpty ? "No public measurements are available yet." : "No measurements match those filters.";
  emptyState.hidden = filtered.length !== 0 || (!catalogueIsEmpty && !filtersAreActive);
}

controls.forEach(control => {control.disabled = true;});
list.setAttribute("aria-busy", "true");
fetch("data/measurements.json")
  .then(response => { if (!response.ok) throw new Error(response.status); return response.json(); })
  .then(data => {
    if (!Array.isArray(data.measurements)) throw new Error("Invalid measurement catalogue");
    measurements = data.measurements.map(item => ({...item,_search:searchText(item)}));
    const groups = [...new Set(measurements.map(item => item.environmentGroup))].sort();
    environmentFilter.replaceChildren(new Option("All environments", ""));
    for (const group of groups) environmentFilter.add(new Option(titleCase(group), group));
    render();
    measurementCount.textContent = measurements.length;
    locationCount.textContent = measurements.filter(item => item.location?.city || item.location?.country).length;
    errorState.hidden = true;
    controls.forEach(control => {control.disabled = false;});
    list.setAttribute("aria-busy", "false");
  })
  .catch(() => {
    list.setAttribute("aria-busy", "false");
    errorState.hidden = false;
  });

controls.forEach(control => control.addEventListener("input", render));
