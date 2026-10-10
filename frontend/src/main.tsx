import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "./app/router";
import "./shared/styles/tokens.css";
import "./shared/styles/base.css";

createRoot(document.getElementById("root")!).render(<RouterProvider router={router} />);
