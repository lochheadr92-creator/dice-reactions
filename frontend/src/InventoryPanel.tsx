import React, { useMemo, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { COLORS, FONTS } from "./theme";
import {
  InvItem,
  InventoryModel,
  SLOT_LABEL,
  Slot,
  itemActionText,
  itemActions,
  parseLedger,
} from "./inventory";

type Props = {
  ledger: Record<string, unknown>;
  summary?: string;
  conditions?: string;
  characterName?: string | null;
  busy?: boolean;
  /** Receives the action sentence for an item. The screen puts it in the action box and sends nothing. */
  onAct: (text: string) => void;
  onClose: () => void;
  onCheckInStory: () => void;
};

// Figure layout: three columns around the body.
const LEFT: Slot[] = ["mainHand", "hands", "belt"];
const CENTER: Slot[] = ["head", "body", "feet"];
const RIGHT: Slot[] = ["offHand", "back"];

export default function InventoryPanel({ ledger, summary, conditions, characterName, busy, onAct, onClose, onCheckInStory }: Props) {
  const model: InventoryModel = useMemo(() => parseLedger(ledger), [ledger]);
  const [picked, setPicked] = useState<InvItem | null>(null);

  const equippedIds = useMemo(() => {
    const ids = new Set<string>();
    (Object.keys(model.slots) as Slot[]).forEach((s) => model.slots[s].forEach((i) => ids.add(i.id)));
    return ids;
  }, [model]);

  // Tapping an item puts a default sentence in the action box straight away. The buttons below
  // swap it for another one. Nothing is sent from here.
  const pick = (item: InvItem) => {
    setPicked(item);
    onAct(itemActionText(item.category === "Worn" ? "examine" : "use", item, equippedIds.has(item.id)));
  };

  const renderSlot = (slot: Slot) => {
    const items = model.slots[slot];
    return (
      <View key={slot} style={[s.slot, items.length ? s.slotFilled : null]} testID={`slot-${slot}`}>
        <Text style={s.slotLabel}>{SLOT_LABEL[slot]}</Text>
        {items.length === 0 ? (
          <Text style={s.slotEmpty}>empty</Text>
        ) : (
          items.slice(0, 3).map((it) => (
            <TouchableOpacity key={it.id} onPress={() => pick(it)} testID={`slot-item-${it.id}`} accessibilityRole="button" accessibilityLabel={`${it.name}, ${SLOT_LABEL[slot]}`}>
              <Text style={[s.slotItem, picked?.id === it.id ? s.slotItemPicked : null]} numberOfLines={2}>
                {it.qty ? `${it.qty}× ` : ""}
                {it.name}
              </Text>
            </TouchableOpacity>
          ))
        )}
        {items.length > 3 ? <Text style={s.slotMore}>{`+${items.length - 3} more below`}</Text> : null}
      </View>
    );
  };

  if (model.empty && !summary && !conditions) {
    return (
      <View testID="inventory-empty">
        <Text style={s.empty}>You are carrying nothing the story has recorded yet.</Text>
        <TouchableOpacity style={s.checkBtn} onPress={onCheckInStory} disabled={busy} testID="ledger-check-action">
          <Text style={s.checkText}>[ CHECK · GEAR · IN · STORY ]</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View testID="inventory-panel">
      <Text style={s.who} testID="inventory-who">{characterName ? characterName.toUpperCase() : "YOU"}</Text>

      <View style={s.figureWrap} testID="inventory-figure">
        <View style={s.silhouette} pointerEvents="none">
          <View style={s.sHead} />
          <View style={s.sTorso} />
          <View style={s.sLegs} />
        </View>
        <View style={s.col}>{LEFT.map(renderSlot)}</View>
        <View style={s.col}>{CENTER.map(renderSlot)}</View>
        <View style={s.col}>{RIGHT.map(renderSlot)}</View>
      </View>

      {model.load ? (
        <Text style={s.load} testID="inventory-load">{`LOAD · ${model.load.toUpperCase()}`}</Text>
      ) : null}

      {picked ? (
        <View style={s.actionBar} testID="inventory-actions">
          <Text style={s.actionTitle} numberOfLines={2}>{`${picked.qty ? `${picked.qty}× ` : ""}${picked.name}`}</Text>
          {picked.uncertain ? <Text style={s.uncertain}>The story is not sure you still have this.</Text> : null}
          <View style={s.actionRow}>
            {itemActions(picked, equippedIds.has(picked.id)).map((a) => (
              <TouchableOpacity
                key={a.key}
                style={s.actionBtn}
                onPress={() => onAct(itemActionText(a.key, picked, equippedIds.has(picked.id)))}
                testID={`inv-act-${a.key}`}
              >
                <Text style={s.actionText}>{a.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={s.hint} testID="inventory-added-hint">
            Added to your action box. Pick another button to change it, or close this and add more before you send.
          </Text>
          <TouchableOpacity style={s.doneBtn} onPress={onClose} testID="inventory-done">
            <Text style={s.actionText}>DONE · BACK TO THE ACTION BOX</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <Text style={s.hint}>Tap an item and a line about it goes into your action box. Nothing is sent until you send it.</Text>
      )}

      {model.groups.map((g) => (
        <View key={g.key} style={s.group} testID={`ledger-${g.key}`}>
          <Text style={s.groupLabel}>{g.label}</Text>
          <View style={s.chips}>
            {g.items.map((it) => (
              <TouchableOpacity
                key={it.id}
                style={[s.chip, picked?.id === it.id ? s.chipPicked : null, it.uncertain ? s.chipUncertain : null]}
                onPress={() => pick(it)}
                testID={`inv-item-${it.id}`}
                accessibilityRole="button"
                accessibilityLabel={`${it.name}${it.qty ? `, ${it.qty}` : ""}`}
              >
                <Text style={s.chipText}>
                  {it.qty ? `${it.qty}× ` : ""}
                  {it.name}
                  {it.uncertain ? " ?" : ""}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ))}

      {summary ? (
        <View style={[s.group, s.accent]}>
          <Text style={s.groupLabel}>SUMMARY</Text>
          <Text style={s.note}>{summary}</Text>
        </View>
      ) : null}
      {conditions ? (
        <View style={[s.group, s.accent]}>
          <Text style={s.groupLabel}>CONDITIONS</Text>
          <Text style={s.note}>{conditions}</Text>
        </View>
      ) : null}

      <TouchableOpacity style={s.checkBtn} onPress={onCheckInStory} disabled={busy} testID="ledger-check-action">
        <Text style={s.checkText}>[ CHECK · GEAR · IN · STORY ]</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  who: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 11, letterSpacing: 3, textAlign: "center", marginBottom: 10 },
  figureWrap: { flexDirection: "row", gap: 8, alignItems: "stretch", position: "relative" },
  col: { flex: 1, justifyContent: "space-between", gap: 8 },
  silhouette: { position: "absolute", left: 0, right: 0, top: 0, bottom: 0, alignItems: "center", justifyContent: "center", opacity: 0.18 },
  sHead: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.textSecondary, marginBottom: 4 },
  sTorso: { width: 64, height: 92, borderRadius: 14, backgroundColor: COLORS.textSecondary, marginBottom: 4 },
  sLegs: { width: 46, height: 70, borderRadius: 10, backgroundColor: COLORS.textSecondary },
  slot: { minHeight: 68, borderWidth: 1, borderColor: COLORS.borderDim, backgroundColor: "rgba(10,10,10,0.85)", padding: 8 },
  slotFilled: { borderColor: COLORS.primary, backgroundColor: "rgba(245,158,11,0.10)" },
  slotLabel: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 9, letterSpacing: 2, marginBottom: 3 },
  slotEmpty: { fontFamily: FONTS.bodyItalic, color: COLORS.textMuted, fontSize: 12 },
  slotItem: { fontFamily: FONTS.body, color: COLORS.textPrimary, fontSize: 13, lineHeight: 17, paddingVertical: 1 },
  slotItemPicked: { color: COLORS.primary, textDecorationLine: "underline" },
  slotMore: { fontFamily: FONTS.mono, color: COLORS.textMuted, fontSize: 9, marginTop: 2 },
  load: { fontFamily: FONTS.mono, color: COLORS.textSecondary, fontSize: 11, letterSpacing: 2, textAlign: "center", marginTop: 10 },
  hint: { fontFamily: FONTS.bodyItalic, color: COLORS.textMuted, fontSize: 13, textAlign: "center", marginTop: 12 },
  actionBar: { borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft, padding: 12, marginTop: 12 },
  actionTitle: { fontFamily: FONTS.headingBold, color: COLORS.textPrimary, fontSize: 18 },
  uncertain: { fontFamily: FONTS.bodyItalic, color: COLORS.textSecondary, fontSize: 13, marginTop: 2 },
  actionRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
  actionBtn: { borderWidth: 1, borderColor: COLORS.primary, paddingVertical: 9, paddingHorizontal: 12 },
  doneBtn: { marginTop: 12, paddingVertical: 12, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft, alignItems: "center" },
  actionText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 11, letterSpacing: 2 },
  group: { borderWidth: 1, borderColor: COLORS.borderDim, backgroundColor: COLORS.surfaceDeep, padding: 12, marginTop: 10 },
  accent: { borderColor: COLORS.primary },
  groupLabel: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 10, letterSpacing: 2, marginBottom: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, paddingVertical: 7, paddingHorizontal: 10 },
  chipPicked: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  chipUncertain: { borderStyle: "dashed" },
  chipText: { fontFamily: FONTS.body, color: COLORS.textPrimary, fontSize: 14 },
  note: { fontFamily: FONTS.mono, color: COLORS.textSecondary, fontSize: 12, lineHeight: 18 },
  empty: { fontFamily: FONTS.bodyItalic, color: COLORS.textMuted, fontSize: 14, textAlign: "center", paddingVertical: 30 },
  checkBtn: { marginTop: 16, paddingVertical: 14, borderWidth: 1, borderColor: COLORS.primary, alignItems: "center" },
  checkText: { fontFamily: FONTS.monoBold, color: COLORS.primary, fontSize: 12, letterSpacing: 3 },
});
