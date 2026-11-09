"""Lokale, durchsuchbare Übersicht für eine Ordner-basierte Link-Sammlung.

Die Anwendung verarbeitet Windows-Internetverknüpfungen (Dateien mit der
Endung .url) rekursiv. Mehrere Verknüpfungen auf dieselbe kanonische URL
werden in einem einzigen Ergebnis zusammengefasst; ihre Fundorte bleiben
sichtbar.
"""

from __future__ import annotations

import configparser
import re
import sys
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import PhotoImage, StringVar, TclError, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


APP_TITLE = "Empfehlungsecke"
APP_DIRECTORY = Path(__file__).resolve().parent
WORDMARK_PATH = APP_DIRECTORY / "assets" / "digitegal_wordmark.png"
MARK_PATH = APP_DIRECTORY / "assets" / "digitegal_mark.png"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "000_Empfehlungsecke"
TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref"}
DOWNLOAD_PAGE = "https://digitegal.de/empfehlungsecke/"
COLORS = {
    "canvas": "#F4F7FB",
    "panel": "#FFFFFF",
    "panel_soft": "#F8FAFD",
    "ink": "#172033",
    "muted": "#68748A",
    "line": "#DCE3EF",
    "primary": "#3563E9",
    "primary_hover": "#274EC2",
    "header": "#172B4D",
    "header_muted": "#C9D7F2",
    "folder": "#EEF4FF",
}


@dataclass(frozen=True)
class LinkLocation:
    """Ein Speicherort, an dem ein Link in der Sammlung abgelegt ist."""

    path: str
    label: str


@dataclass
class Recommendation:
    """Eine eindeutige Empfehlung mitsamt allen Kategorien, in denen sie liegt."""

    url: str
    canonical_url: str
    title: str
    locations: list[LinkLocation]

    @property
    def categories(self) -> list[str]:
        return sorted({location.path for location in self.locations}, key=str.casefold)


def normalize_url(value: str) -> str:
    """Erzeugt einen stabilen Vergleichsschlüssel, ohne die Zielseite zu ändern.

    Fragmente und übliche Tracking-Parameter werden ignoriert. Andere
    Query-Parameter bleiben erhalten, weil sie auf unterschiedliche Seiten
    oder Suchergebnisse verweisen können.
    """

    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value.casefold()

    scheme = parts.scheme.casefold()
    hostname = (parts.hostname or "").casefold()
    port = parts.port
    netloc = hostname
    if parts.username:
        credentials = parts.username
        if parts.password:
            credentials += f":{parts.password}"
        netloc = f"{credentials}@{netloc}"
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc += f":{port}"

    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_PARAMETERS and not key.casefold().startswith("utm_")
        ),
        doseq=True,
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def read_shortcut(path: Path) -> str | None:
    """Liest die URL aus einer Windows-Internetverknüpfung robust aus."""

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8-sig")
        url = parser.get("InternetShortcut", "URL", fallback="").strip()
        if url:
            return url
    except (OSError, UnicodeDecodeError, configparser.Error):
        pass

    # Manche alte Verknüpfungen sind nicht sauber kodiert. Diese Fallback-
    # Suche ist absichtlich klein gehalten und liest nur die URL-Zeile.
    try:
        with path.open("r", encoding="latin-1", errors="replace") as handle:
            for line in handle:
                if line.casefold().startswith("url="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def display_title(shortcut: Path, url: str) -> str:
    """Ermittelt einen lesbaren Titel aus dem Dateinamen."""

    name = re.sub(r"^[#\-\s]+", "", shortcut.stem).strip()
    return name or url


def scan_recommendations(root: Path) -> tuple[list[Recommendation], int]:
    """Scannt *root* und führt Links mit gleicher Ziel-URL zusammen.

    Rückgabewert: (eindeutige Empfehlungen, übersprungene Verknüpfungen).
    """

    grouped: dict[str, Recommendation] = {}
    invalid_count = 0
    for shortcut in root.rglob("*"):
        if not shortcut.is_file() or shortcut.suffix.casefold() != ".url":
            continue
        url = read_shortcut(shortcut)
        canonical = normalize_url(url or "")
        if not canonical:
            invalid_count += 1
            continue
        relative_parent = shortcut.parent.relative_to(root).as_posix()
        location = LinkLocation(relative_parent or "Start", shortcut.name)
        if canonical in grouped:
            grouped[canonical].locations.append(location)
        else:
            grouped[canonical] = Recommendation(
                url=url or canonical,
                canonical_url=canonical,
                title=display_title(shortcut, url or canonical),
                locations=[location],
            )

    recommendations = sorted(grouped.values(), key=lambda item: item.title.casefold())
    return recommendations, invalid_count


class RecommendationApp:
    def __init__(self, root: Tk, initial_path: Path):
        self.root = root
        self.root.title(f"DigitEgal {APP_TITLE}")
        self.root.minsize(1050, 660)
        self.root.geometry("1320x820")
        self.root.configure(background=COLORS["canvas"])

        self.folder = initial_path
        self.recommendations: list[Recommendation] = []
        self.visible: list[Recommendation] = []
        self.selected_folder = ""
        self.query = StringVar()
        self.status = StringVar(value="Bereit zum Einlesen.")
        self.path_label = StringVar(value=str(self.folder))
        self.current_path = StringVar(value=f"Pfad  ·  {self.folder.name}")
        self._logo_sources: list[PhotoImage] = []
        self.wordmark_image: PhotoImage | None = None
        self.mark_image: PhotoImage | None = None
        self._load_brand_images()
        self._build_interface()
        self.query.trace_add("write", lambda *_: self.apply_filter())
        self.scan()

    def _build_interface(self) -> None:
        self._configure_styles()
        outer = ttk.Frame(self.root, style="App.TFrame", padding=20)
        outer.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer, style="Header.TFrame", padding=(22, 18))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.grid(row=0, column=0, sticky="w")
        if self.wordmark_image:
            ttk.Label(brand, image=self.wordmark_image, style="HeaderLogo.TLabel").grid(row=0, column=0, sticky="w")
        else:
            ttk.Label(brand, text="DigitEgal", style="FallbackBrand.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(brand, text="Empfehlungsecke", style="Title.TLabel").grid(row=0, column=1, sticky="w", padx=(16, 0))

        header_actions = ttk.Frame(header, style="Header.TFrame")
        header_actions.grid(row=0, column=1, sticky="e")
        if self.mark_image:
            ttk.Label(header_actions, image=self.mark_image, style="HeaderLogo.TLabel").grid(row=0, column=0, padx=(0, 12))
        ttk.Button(
            header_actions,
            text="Aktuelle Sammlung herunterladen  ↗",
            style="HeaderLink.TButton",
            command=self.open_download_page,
        ).grid(row=0, column=1, sticky="e")

        source = ttk.Frame(outer, style="Card.TFrame", padding=12)
        source.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        source.columnconfigure(0, weight=1)
        ttk.Label(source, text="QUELLORDNER", style="FieldLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(source, textvariable=self.path_label, style="Path.TLabel").grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ttk.Button(source, text="Ordner wählen", style="Secondary.TButton", command=self.choose_folder).grid(
            row=0, column=1, rowspan=2, padx=(14, 0)
        )
        ttk.Button(source, text="↻", style="Icon.TButton", command=self.scan).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        search = ttk.Frame(outer, style="Card.TFrame", padding=12)
        search.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="⌕", style="SearchIcon.TLabel").grid(row=0, column=0, padx=(2, 10))
        search_entry = ttk.Entry(search, textvariable=self.query, style="Search.TEntry")
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.focus_set()
        ttk.Button(search, text="Leeren", style="Secondary.TButton", command=lambda: self.query.set("")).grid(
            row=0, column=2, padx=(10, 0)
        )

        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.grid(row=3, column=0, sticky="nsew")
        category_frame = ttk.Labelframe(panes, text="  ORDNERSTRUKTUR  ", style="Panel.TLabelframe", padding=10)
        category_frame.columnconfigure(0, weight=1)
        category_frame.rowconfigure(0, weight=1)
        self.folder_tree = ttk.Treeview(category_frame, show="tree", selectmode="browse")
        folder_scrollbar = ttk.Scrollbar(category_frame, orient="vertical", command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=folder_scrollbar.set)
        self.folder_tree.grid(row=0, column=0, sticky="nsew")
        folder_scrollbar.grid(row=0, column=1, sticky="ns")
        self.folder_tree.bind("<<TreeviewSelect>>", self.select_folder)
        panes.add(category_frame, weight=1)

        result_frame = ttk.Labelframe(panes, text="  INHALT  ", style="Panel.TLabelframe", padding=10)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)
        ttk.Label(result_frame, textvariable=self.current_path, style="CurrentPath.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 9)
        )
        self.results = ttk.Treeview(
            result_frame,
            columns=("title", "url", "locations"),
            show="headings",
            selectmode="browse",
        )
        self.results.heading("title", text="Empfehlung")
        self.results.heading("url", text="Webseite")
        self.results.heading("locations", text="Fundorte")
        self.results.column("title", width=280, minwidth=170)
        self.results.column("url", width=420, minwidth=200)
        self.results.column("locations", width=85, minwidth=70, anchor="center")
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.results.yview)
        self.results.configure(yscrollcommand=scrollbar.set)
        self.results.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.results.bind("<<TreeviewSelect>>", self.show_details)
        self.results.bind("<Double-1>", lambda _event: self.open_selected())
        self.results.tag_configure("folder", background=COLORS["folder"], foreground="#31527F")
        panes.add(result_frame, weight=4)

        self.details = ttk.Labelframe(outer, text="  DETAILS  ", style="Panel.TLabelframe", padding=10)
        self.details.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.details.columnconfigure(0, weight=1)
        self.detail_text = ScrolledText(
            self.details,
            height=5,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 10),
            background=COLORS["panel_soft"],
            foreground=COLORS["ink"],
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        self.detail_text.grid(row=0, column=0, sticky="ew")
        action_bar = ttk.Frame(self.details, style="Card.TFrame")
        action_bar.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Button(action_bar, text="Webseite öffnen  ↗", style="Accent.TButton", command=self.open_selected).grid(row=0, column=0)

        ttk.Label(outer, textvariable=self.status, style="Status.TLabel").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.details.grid_remove()

    def _configure_styles(self) -> None:
        """Definiert eine eigenständige, helle Oberfläche ohne Zusatzpakete."""

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["canvas"])
        style.configure("Header.TFrame", background=COLORS["header"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["canvas"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=COLORS["header"], foreground="white", font=("Segoe UI", 20, "bold"))
        style.configure("HeaderLogo.TLabel", background=COLORS["header"])
        style.configure("FallbackBrand.TLabel", background=COLORS["header"], foreground="#30B6EE", font=("Segoe UI", 24, "bold", "italic"))
        style.configure("HeaderLink.TButton", background="#23416E", foreground="#E4EEFF", font=("Segoe UI", 9, "bold"), padding=(13, 8))
        style.map("HeaderLink.TButton", background=[("active", "#315686")])
        style.configure("FieldLabel.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 8, "bold"))
        style.configure("Path.TLabel", background=COLORS["panel"], foreground=COLORS["ink"], font=("Segoe UI", 10))
        style.configure("CurrentPath.TLabel", background=COLORS["panel"], foreground=COLORS["primary"], font=("Segoe UI", 9, "bold"))
        style.configure("SearchIcon.TLabel", background=COLORS["panel"], foreground=COLORS["primary"], font=("Segoe UI", 16))
        style.configure("Status.TLabel", background=COLORS["canvas"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(11, 7), borderwidth=0)
        style.configure("Accent.TButton", background=COLORS["primary"], foreground="white")
        style.map("Accent.TButton", background=[("active", COLORS["primary_hover"])])
        style.configure("Secondary.TButton", background="#EAF0FA", foreground="#29456E")
        style.map("Secondary.TButton", background=[("active", "#DCE7F8")])
        style.configure("Icon.TButton", background="#EAF0FA", foreground=COLORS["primary"], font=("Segoe UI", 13, "bold"), padding=(9, 4))
        style.map("Icon.TButton", background=[("active", "#DCE7F8")])
        style.configure("Search.TEntry", fieldbackground=COLORS["panel_soft"], foreground=COLORS["ink"], padding=(10, 9), bordercolor=COLORS["line"], lightcolor=COLORS["primary"])
        style.map("Search.TEntry", bordercolor=[("focus", COLORS["primary"])])
        style.configure("Panel.TLabelframe", background=COLORS["panel"], bordercolor=COLORS["line"], relief="solid", borderwidth=1)
        style.configure("Panel.TLabelframe.Label", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 8, "bold"))
        style.configure("Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["ink"], rowheight=34, borderwidth=0, font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", "#DCE8FF")], foreground=[("selected", "#173B74")])
        style.configure("Treeview.Heading", background="#EFF3F9", foreground="#53627B", font=("Segoe UI", 9, "bold"), relief="flat", padding=(10, 9))
        style.map("Treeview.Heading", background=[("active", "#E4EBF6")])
        style.configure("TScrollbar", background="#D9E1ED", troughcolor=COLORS["panel"], bordercolor=COLORS["panel"], arrowsize=12)

    def _load_brand_images(self) -> None:
        """Lädt die mitgelieferten Logos und skaliert sie passend für den Kopf."""

        try:
            wordmark_source = PhotoImage(file=str(WORDMARK_PATH))
            mark_source = PhotoImage(file=str(MARK_PATH))
            self._logo_sources.extend((wordmark_source, mark_source))
            self.wordmark_image = wordmark_source.subsample(10, 10)
            self.mark_image = mark_source.subsample(40, 40)
            self.root.iconphoto(True, mark_source)
        except (TclError, OSError):
            # Die Oberfläche bleibt bei einem fehlenden Asset nutzbar und
            # verwendet dann den textuellen Marken-Fallback.
            self.wordmark_image = None
            self.mark_image = None

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, initialdir=self.folder, title="Ordner mit Link-Sammlung wählen")
        if selected:
            self.folder = Path(selected)
            self.path_label.set(str(self.folder))
            self._update_current_path_label()
            self.scan()

    def open_download_page(self) -> None:
        """Öffnet die zentrale Download-Seite für aktualisierte Empfehlungen."""

        webbrowser.open_new_tab(DOWNLOAD_PAGE)

    def scan(self) -> None:
        if not self.folder.is_dir():
            messagebox.showerror(APP_TITLE, f"Der Ordner existiert nicht:\n{self.folder}")
            return
        self.status.set("Lese Verknüpfungen ein …")
        self.root.update_idletasks()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            recommendations, invalid_count = scan_recommendations(self.folder)
            self.root.after(0, self.finish_scan, recommendations, invalid_count, None)
        except OSError as error:
            self.root.after(0, self.finish_scan, [], 0, error)

    def finish_scan(self, recommendations: list[Recommendation], invalid_count: int, error: OSError | None) -> None:
        if error:
            messagebox.showerror(APP_TITLE, f"Beim Einlesen ist ein Fehler aufgetreten:\n{error}")
            self.status.set("Einlesen fehlgeschlagen.")
            return
        self.recommendations = recommendations
        self._build_folder_tree()
        total_shortcuts = sum(len(item.locations) for item in recommendations)
        self.status.set(
            f"{len(recommendations):,} eindeutige Empfehlungen aus {total_shortcuts:,} Verknüpfungen"
            + (f" · {invalid_count} ohne URL übersprungen" if invalid_count else "")
        )
        self.apply_filter()

    def _build_folder_tree(self) -> None:
        """Bildet alle Ordnerpfade als auswählbaren, verschachtelten Baum ab."""

        self.folder_tree.delete(*self.folder_tree.get_children())
        root_id = "__root__"
        self.folder_tree.insert("", "end", iid=root_id, text=self.folder.name or str(self.folder), open=True)
        known_nodes = {root_id}
        # Der Baum soll die echte Ordnerstruktur zeigen – auch dann, wenn ein
        # Unterordner momentan noch keine Verknüpfung enthält.
        paths = {
            directory.relative_to(self.folder).as_posix()
            for directory in self.folder.rglob("*")
            if directory.is_dir()
        }
        for path in sorted(paths, key=lambda item: (item.casefold().count("/"), item.casefold())):
            parent = root_id
            parts: list[str] = []
            for part in path.split("/"):
                parts.append(part)
                node_id = "/".join(parts)
                if node_id not in known_nodes:
                    self.folder_tree.insert(parent, "end", iid=node_id, text=part, open=False)
                    known_nodes.add(node_id)
                parent = node_id
        self.selected_folder = ""
        self.folder_tree.selection_set(root_id)
        self.folder_tree.focus(root_id)
        self._update_current_path_label()

    def _update_current_path_label(self) -> None:
        segments = self.selected_folder.split("/") if self.selected_folder else []
        readable_path = "  ›  ".join([self.folder.name, *segments])
        self.current_path.set(f"PFAD  ·  {readable_path}")

    def select_folder(self, _event: object | None = None) -> None:
        selection = self.folder_tree.selection()
        if not selection:
            return
        self.selected_folder = "" if selection[0] == "__root__" else selection[0]
        self._update_current_path_label()
        self.apply_filter()

    def _is_in_selected_folder(self, location: LinkLocation) -> bool:
        return not self.selected_folder or location.path == self.selected_folder or location.path.startswith(
            f"{self.selected_folder}/"
        )

    def _is_directly_in_selected_folder(self, location: LinkLocation) -> bool:
        """Prüft, ob eine Verknüpfung direkt im aktuell geöffneten Ordner liegt."""

        return location.path == (self.selected_folder or "Start")

    def _matching_folder_paths(self, words: list[str]) -> set[str]:
        """Ermittelt Unterordner, die selbst zum Suchbegriff passen."""

        current_folder = self.folder / self.selected_folder
        try:
            directories = (item for item in current_folder.rglob("*") if item.is_dir())
            return {
                directory.relative_to(self.folder).as_posix()
                for directory in directories
                if all(word in directory.relative_to(self.folder).as_posix().casefold() for word in words)
            }
        except OSError:
            return set()

    def _add_folder_and_parents(self, folders: set[str], path: str) -> None:
        """Fügt einen Fundordner samt sichtbarem Pfad bis zum Treffer hinzu."""

        if path == "Start":
            return
        parts = path.split("/")
        start_at = len(self.selected_folder.split("/")) + 1 if self.selected_folder else 1
        for position in range(start_at, len(parts) + 1):
            folder_path = "/".join(parts[:position])
            folders.add(folder_path)

    def _open_folder(self, folder_path: str) -> None:
        """Öffnet einen Ordner aus der rechten Inhaltsansicht."""

        self.selected_folder = folder_path
        self.folder_tree.selection_set(folder_path)
        self.folder_tree.focus(folder_path)
        self.folder_tree.see(folder_path)
        self._update_current_path_label()
        self.apply_filter()

    def _show_folder_contents(self) -> None:
        """Zeigt ohne Suchbegriff Ordner und Links des aktuellen Pfads an."""

        current_folder = self.folder / self.selected_folder
        try:
            child_folders = sorted(
                (item for item in current_folder.iterdir() if item.is_dir()), key=lambda item: item.name.casefold()
            )
        except OSError:
            child_folders = []

        for child in child_folders:
            relative_path = child.relative_to(self.folder).as_posix()
            self.results.insert(
                "", "end", iid=f"folder:{relative_path}", values=(f"📁  {child.name}", "Ordner", ""), tags=("folder",)
            )

        self.visible = [
            recommendation
            for recommendation in self.recommendations
            if any(self._is_directly_in_selected_folder(location) for location in recommendation.locations)
        ]
        for position, recommendation in enumerate(self.visible):
            self.results.insert(
                "",
                "end",
                iid=f"link:{position}",
                values=(recommendation.title, recommendation.url, len(recommendation.locations)),
            )

        current_name = self.selected_folder or self.folder.name
        self._hide_details_panel()
        self.status.set(f"{len(child_folders)} Unterordner · {len(self.visible)} eindeutige Links in {current_name}")

    def apply_filter(self) -> None:
        words = self.query.get().casefold().split()
        self.visible = []
        self.results.delete(*self.results.get_children())
        self._hide_details_panel()
        if not words:
            self._show_folder_contents()
            return

        searched_in = 0
        matching_folders = self._matching_folder_paths(words)
        for recommendation in self.recommendations:
            matching_locations = [location for location in recommendation.locations if self._is_in_selected_folder(location)]
            if not matching_locations:
                continue
            searched_in += 1
            searchable = " ".join(
                [recommendation.title, recommendation.url, *(item.path for item in matching_locations), *(item.label for item in matching_locations)]
            ).casefold()
            if all(word in searchable for word in words):
                self.visible.append(recommendation)
                for location in matching_locations:
                    self._add_folder_and_parents(matching_folders, location.path)

        for folder_path in sorted(matching_folders, key=lambda item: (item.count("/"), item.casefold())):
            display_path = folder_path
            if self.selected_folder and folder_path.startswith(f"{self.selected_folder}/"):
                display_path = folder_path.removeprefix(f"{self.selected_folder}/")
            self.results.insert(
                "",
                "end",
                iid=f"folder:{folder_path}",
                values=(f"📁  {display_path.replace('/', '  ›  ')}", "Ordner", ""),
                tags=("folder",),
            )

        for position, recommendation in enumerate(self.visible):
            self.results.insert(
                "",
                "end",
                iid=f"link:{position}",
                values=(recommendation.title, recommendation.url, len(recommendation.locations)),
            )
        if self.visible:
            self.results.selection_set("0")
            self.results.focus("0")
            self.show_details()
        else:
            self._hide_details_panel()
        self.status.set(
            f"{len(matching_folders):,} passende Unterordner · {len(self.visible):,} Link-Treffer in {searched_in:,} Empfehlungen"
        )

    def selected_recommendation(self) -> Recommendation | None:
        selection = self.results.selection()
        if not selection or not selection[0].startswith("link:"):
            return None
        return self.visible[int(selection[0].removeprefix("link:"))]

    def show_details(self, _event: object | None = None) -> None:
        selection = self.results.selection()
        if selection and selection[0].startswith("folder:"):
            self._open_folder(selection[0].removeprefix("folder:"))
            return
        recommendation = self.selected_recommendation()
        if recommendation is None:
            self._hide_details_panel()
            return
        locations = "\n".join(f"• {location.path}  ›  {location.label}" for location in recommendation.locations)
        self._show_details_panel(len(recommendation.locations))
        self._set_details(f"{recommendation.url}\n\nFundorte ({len(recommendation.locations)}):\n{locations}")

    def _show_details_panel(self, location_count: int) -> None:
        """Blendet Details nur bei einer Link-Auswahl und passend groß ein."""

        self.detail_text.configure(height=min(10, max(5, location_count + 3)))
        self.details.grid()

    def _hide_details_panel(self) -> None:
        self.details.grid_remove()

    def _set_details(self, value: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", value)
        self.detail_text.configure(state="disabled")

    def open_selected(self) -> None:
        selection = self.results.selection()
        if selection and selection[0].startswith("folder:"):
            self._open_folder(selection[0].removeprefix("folder:"))
            return
        recommendation = self.selected_recommendation()
        if recommendation:
            webbrowser.open_new_tab(recommendation.url)


def main() -> None:
    initial_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_ROOT
    root = Tk()
    RecommendationApp(root, initial_path)
    root.mainloop()


if __name__ == "__main__":
    main()
