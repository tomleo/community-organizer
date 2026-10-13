import "trix";
import "trix/dist/trix.css";
import "./manage.scss";

// Event photos are uploaded separately; ignore files dropped or pasted into the editor.
document.addEventListener("trix-file-accept", (event) => event.preventDefault());
