import type { RouteObject } from "react-router";
import { paths } from "../../app/paths";
import { LoginPage } from "./pages/LoginPage";

export const identityRoutes: RouteObject[] = [{ path: paths.login, element: <LoginPage /> }];
