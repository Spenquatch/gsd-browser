import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SessionsPage } from "./pages/SessionsPage";
import { LiveSessionPage } from "./pages/LiveSessionPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<SessionsPage />} />
        <Route path="sessions/:id" element={<LiveSessionPage />} />
      </Route>
    </Routes>
  );
}
