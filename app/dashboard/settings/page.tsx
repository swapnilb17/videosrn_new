import { Card } from "@/components/ui/card";
import { pricingTiers } from "@/lib/mock-data";

export default function SettingsPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <Card className="space-y-2">
        <p className="text-lg font-semibold">Workspace Preferences</p>
        <p className="text-sm text-slate-300">
          Defaults for voice, aspect ratio, and style presets can be configured here.
        </p>
      </Card>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Pricing tiers</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {pricingTiers.map((tier) => (
            <Card key={tier.name} className="space-y-2">
              <p className="font-semibold">{tier.name}</p>
              <p className="text-xl font-bold">{tier.price}</p>
              <p className="text-sm text-orange-200">{tier.credits}</p>
              <p className="text-sm text-slate-300">{tier.description}</p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
