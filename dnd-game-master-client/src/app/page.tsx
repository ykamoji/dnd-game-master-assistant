import { GameStage } from "@/components/game/GameStage";
import { GameProvider } from "@/context/GameContext";

export default function AppRoot() {
  return (
    <main className="h-screen w-full overflow-hidden">
      <GameProvider>
        <GameStage />
      </GameProvider>
    </main>
  );
}
