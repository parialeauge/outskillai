import { BrowserRouter, Route, Routes } from "react-router-dom";
import Chrome from "./components/Chrome";
import Admin from "./pages/Admin";
import Client from "./pages/Client";
import Landing from "./pages/Landing";

export default function App() {
  return (
    <BrowserRouter>
      <Chrome />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/client" element={<Client />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  );
}
