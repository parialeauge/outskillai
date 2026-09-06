import { BrowserRouter, Route, Routes } from "react-router-dom";
import Chrome from "./components/Chrome";
import Admin from "./pages/Admin";
import Client from "./pages/Client";
import ConstellationLanding from "./pages/ConstellationLanding";
import Landing from "./pages/Landing";

export default function App() {
  return (
    <BrowserRouter>
      <Chrome />
      <Routes>
        <Route path="/" element={<ConstellationLanding />} />
        <Route path="/app" element={<Landing />} />
        <Route path="/client" element={<Client />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  );
}
