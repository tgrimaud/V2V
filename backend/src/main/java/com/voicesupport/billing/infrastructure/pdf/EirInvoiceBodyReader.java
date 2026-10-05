package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.valueobject.DateRange;
import com.voicesupport.billing.domain.model.valueobject.Evidence;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

// Reads the "Detail of your eir service" body into the domain section -> group -> item tree
// (TASK-BE-065). The body is a flat line sequence; this single pass tracks the current section and
// group. Precedence per line: group header -> subtotal (closes the group) -> item (trailing amount) ->
// service metadata (UAN / identifier, skipped) -> otherwise a new service section header. Category is
// inferred per group: a negative/"discount" line is DISCOUNT, a one-time-group line is ONE_OFF, a
// "from X until Y" line is PRORATA, the first remaining recurring line is SUBSCRIPTION, the rest OPTION.
final class EirInvoiceBodyReader {

    private static final String BODY_START = "Detail of your eir service";

    private final List<InvoiceSection> sections = new ArrayList<>();
    private final String documentReference;
    private final Map<String, Integer> codeCounts = new HashMap<>();
    private SectionDraft section;
    private GroupDraft group;
    private int lineCounter;

    EirInvoiceBodyReader(String documentReference) {
        this.documentReference = documentReference;
    }

    List<InvoiceSection> read(List<String> lines) {
        boolean inBody = false;
        for (String line : lines) {
            if (!inBody) {
                inBody = line.equals(BODY_START);
                continue;
            }
            if (isBodyEnd(line)) {
                break;
            }
            consume(line);
        }
        closeGroup();
        closeSection();
        return List.copyOf(sections);
    }

    private void consume(String line) {
        if (line.isBlank() || isNoise(line)) {
            return;
        }
        EirInvoiceText.GroupHeader header = EirInvoiceText.groupHeader(line);
        if (header != null) {
            openGroup(header);
        } else if (EirInvoiceText.isSubtotal(line)) {
            closeGroup();
        } else if (group != null && EirInvoiceText.trailingAmountCents(line) != null) {
            addItem(line);
        } else if (!isServiceMetadata(line)) {
            openSection(line);
        }
    }

    private void openSection(String name) {
        closeGroup();
        closeSection();
        section = new SectionDraft(name, sections.size());
    }

    private void openGroup(EirInvoiceText.GroupHeader header) {
        closeGroup();
        group = new GroupDraft(header.name(), header.period(),
                header.name().startsWith("One-time"), sections.size(), sectionGroupCount());
    }

    private void addItem(String line) {
        long cents = EirInvoiceText.trailingAmountCents(line);
        String label = EirInvoiceText.stripTrailingAmount(line);
        DateRange period = EirInvoiceText.linePeriod(label);
        LineCategory category = group.classify(cents, label);
        Evidence evidence = new Evidence("pdfbox-eir", documentReference, label);
        group.items.add(new InvoiceItem("line-" + (++lineCounter), null, uniqueCode(label), null,
                category, EirInvoiceText.amount23(cents), evidence, period));
    }

    // Stable, invoice-unique product code from the label slug (BUG-028): the first occurrence keeps the
    // bare slug (so the same product matches across months), repeats get a numeric suffix so no line is
    // ever collapsed. Falls back to "line" when a label slugs to empty.
    private String uniqueCode(String label) {
        String base = EirInvoiceText.slug(label);
        if (base.isEmpty()) {
            base = "line";
        }
        int occurrence = codeCounts.merge(base, 1, Integer::sum);
        return occurrence == 1 ? base : base + "-" + occurrence;
    }

    private void closeGroup() {
        if (group != null && section != null) {
            section.groups.add(group.toGroup());
        }
        group = null;
    }

    private void closeSection() {
        if (section != null && !section.groups.isEmpty()) {
            sections.add(section.toSection());
        }
        section = null;
    }

    private int sectionGroupCount() {
        return section == null ? 0 : section.groups.size();
    }

    private static boolean isBodyEnd(String line) {
        return line.startsWith("VAT Rate") || line.startsWith("Page ") || line.startsWith("-- ");
    }

    private static boolean isNoise(String line) {
        return line.startsWith("Billing account") || line.startsWith("Bill number")
                || line.startsWith("Billing date") || line.startsWith("Payments & Adjustments")
                || line.startsWith("There were no transactions");
    }

    private static boolean isServiceMetadata(String line) {
        return line.contains("UAN:") || line.contains("service identifier");
    }

    private static final class SectionDraft {
        private final String name;
        private final int order;
        private final List<InvoiceGroup> groups = new ArrayList<>();

        private SectionDraft(String name, int order) {
            this.name = name;
            this.order = order;
        }

        private InvoiceSection toSection() {
            List<LineAmounts> parts = groups.stream().map(InvoiceGroup::amounts).toList();
            return new InvoiceSection("sec-" + order, name, order, true, EirInvoiceText.rollup(parts), groups);
        }
    }

    private static final class GroupDraft {
        private final String name;
        private final DateRange period;
        private final boolean oneOff;
        private final int sectionOrder;
        private final int order;
        private final List<InvoiceItem> items = new ArrayList<>();
        private boolean subscriptionAssigned;

        private GroupDraft(String name, DateRange period, boolean oneOff, int sectionOrder, int order) {
            this.name = name;
            this.period = period;
            this.oneOff = oneOff;
            this.sectionOrder = sectionOrder;
            this.order = order;
        }

        private LineCategory classify(long cents, String label) {
            if (cents < 0 || label.toLowerCase().contains("discount")) {
                return LineCategory.DISCOUNT;
            }
            if (oneOff) {
                return LineCategory.ONE_OFF;
            }
            if (EirInvoiceText.linePeriod(label) != null) {
                return LineCategory.PRORATA;
            }
            if (!subscriptionAssigned) {
                subscriptionAssigned = true;
                return LineCategory.SUBSCRIPTION;
            }
            return LineCategory.OPTION;
        }

        private InvoiceGroup toGroup() {
            List<LineAmounts> parts = items.stream().map(InvoiceItem::amounts).toList();
            return new InvoiceGroup("grp-" + sectionOrder + "-" + order, name, null, order,
                    EirInvoiceText.rollup(parts), items, period);
        }
    }
}
