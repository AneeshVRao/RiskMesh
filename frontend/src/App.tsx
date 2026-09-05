import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Nav } from "./components/Nav";
import { ControlCenter } from "./pages/ControlCenter";
import { Investigator } from "./pages/Investigator";
import { Threshold } from "./pages/Threshold";
import { Benchmark } from "./pages/Benchmark";

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main className="mx-auto max-w-[1440px] p-2">
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/investigator" element={<Investigator />} />
          <Route path="/investigator/:componentId" element={<Investigator />} />
          <Route path="/threshold" element={<Threshold />} />
          <Route path="/benchmark" element={<Benchmark />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
